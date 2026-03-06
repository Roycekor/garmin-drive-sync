# scripts/fit_analyzer.py
from fitparse import FitFile
import pandas as pd
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

def fit_to_dataframe(fit_path):
    fitfile = FitFile(fit_path)
    records = []
    for record in fitfile.get_messages('record'):
        r = {}
        for field in record:
            r[field.name] = field.value
        records.append(r)
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
    return df

def zone2_summary(df, hr_low=137, hr_high=156):
    if df.empty or 'heart_rate' not in df.columns:
        return {'zone2_seconds': 0, 'zone2_avg_speed_kmh': None, 'zone2_avg_pace_min_km': None}
    zone2 = df[(df['heart_rate'] >= hr_low) & (df['heart_rate'] <= hr_high)]
    if zone2.empty:
        return {'zone2_seconds': 0, 'zone2_avg_speed_kmh': None, 'zone2_avg_pace_min_km': None}
    # Garmin FIT 파일에서는 'enhanced_speed' 필드를 사용 (단위: m/s → km/h 변환)
    speed_col = 'enhanced_speed' if 'enhanced_speed' in zone2.columns else 'speed'
    if speed_col not in zone2.columns:
        return {'zone2_seconds': int(len(zone2)), 'zone2_avg_speed_kmh': None, 'zone2_avg_pace_min_km': None}
    avg_speed_ms = zone2[speed_col].mean()
    # m/s를 km/h로 변환 (1 m/s = 3.6 km/h)
    avg_speed_kmh = avg_speed_ms * 3.6 if pd.notna(avg_speed_ms) else None
    # km/h를 min/km로 변환 (러닝 pace)
    avg_pace_min_km = 60 / avg_speed_kmh if avg_speed_kmh and avg_speed_kmh > 0 else None
    
    # 포맷팅
    formatted_speed_kmh = float(round(avg_speed_kmh, 2)) if avg_speed_kmh is not None else None
    formatted_pace = None
    if avg_pace_min_km is not None:
        minutes = int(avg_pace_min_km)
        seconds = round((avg_pace_min_km - minutes) * 60)
        formatted_pace = f"{minutes}:{seconds:02d}"
    
    return {
        'zone2_seconds': int(len(zone2)),
        'zone2_avg_speed_kmh': formatted_speed_kmh,
        'zone2_avg_pace_min_km': formatted_pace
    }

def save_zone2_analysis(db_path, filename, analysis_result):
    """Zone2 분석 결과를 SQLite 데이터베이스에 저장"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 테이블 생성 (없으면)
    cursor.execute('''CREATE TABLE IF NOT EXISTS zone2_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        zone2_seconds INTEGER,
        zone2_avg_speed_kmh REAL,
        zone2_avg_pace_min_km TEXT,
        analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # 중복 방지: 같은 파일명으로 이미 분석된 게 있으면 업데이트
    cursor.execute('''INSERT OR REPLACE INTO zone2_analysis 
        (filename, zone2_seconds, zone2_avg_speed_kmh, zone2_avg_pace_min_km, analyzed_at)
        VALUES (?, ?, ?, ?, ?)''', 
        (filename, 
         analysis_result['zone2_seconds'], 
         analysis_result['zone2_avg_speed_kmh'], 
         analysis_result['zone2_avg_pace_min_km'],
         datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    logger.info(f"Zone2 분석 결과 DB에 저장: {filename}")
