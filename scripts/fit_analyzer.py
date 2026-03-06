# scripts/fit_analyzer.py
from fitparse import FitFile
import pandas as pd
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

def get_fit_sport(fit_path):
    """FIT 파일에서 sport 타입을 추출 (예: 'running', 'cycling')"""
    fitfile = FitFile(fit_path)
    for msg in fitfile.get_messages('sport'):
        for field in msg:
            if field.name == 'sport':
                return field.value
    return None


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
    
    zone2_ratio = len(zone2) / len(df) * 100 if len(df) > 0 else 0

    return {
        'zone2_seconds': int(len(zone2)),
        'zone2_ratio': round(zone2_ratio, 1),
        'zone2_avg_speed_kmh': formatted_speed_kmh,
        'zone2_avg_pace_min_km': formatted_pace
    }

def run_summary(df):
    """활동 전체 요약 추출"""
    if df.empty or 'timestamp' not in df.columns:
        return {}
    result = {
        'activity_date': str(df['timestamp'].iloc[0].date()),
        'total_duration_sec': int((df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).total_seconds()),
    }
    if 'distance' in df.columns:
        result['total_distance_km'] = round(df['distance'].iloc[-1] / 1000, 2)
    if 'heart_rate' in df.columns:
        result['avg_hr'] = round(df['heart_rate'].mean(), 1)
        result['max_hr'] = int(df['heart_rate'].max())
    if 'cadence' in df.columns:
        result['avg_cadence'] = round(df['cadence'].mean(), 1)
    return result


def hr_drift(df):
    """전반부/후반부 HR 비교로 HR drift % 계산"""
    if df.empty or 'heart_rate' not in df.columns or 'timestamp' not in df.columns:
        return None
    mid = len(df) // 2
    if mid < 10:
        return None
    avg_hr_1st = df['heart_rate'].iloc[:mid].mean()
    avg_hr_2nd = df['heart_rate'].iloc[mid:].mean()
    if avg_hr_1st == 0 or pd.isna(avg_hr_1st):
        return None
    return round(((avg_hr_2nd / avg_hr_1st) - 1) * 100, 2)


def pace_stability(df, min_distance_km=8):
    """1km 구간별 페이스의 변동계수(CV) 계산. 10km 미만 활동은 None 반환"""
    if df.empty or 'distance' not in df.columns or 'timestamp' not in df.columns:
        return None
    total_dist = df['distance'].iloc[-1] / 1000
    if total_dist < min_distance_km:
        return None

    # 1km 구간별 페이스 계산
    km_paces = []
    km_mark = 1.0
    prev_idx = 0
    for i in range(1, len(df)):
        dist_km = df['distance'].iloc[i] / 1000
        if dist_km >= km_mark:
            seg = df.iloc[prev_idx:i + 1]
            seg_time = (seg['timestamp'].iloc[-1] - seg['timestamp'].iloc[0]).total_seconds()
            seg_dist = (seg['distance'].iloc[-1] - seg['distance'].iloc[0]) / 1000
            if seg_dist > 0 and seg_time > 0:
                pace = seg_time / seg_dist / 60  # min/km
                km_paces.append(pace)
            prev_idx = i
            km_mark += 1.0

    if len(km_paces) < 3:
        return None
    paces = pd.Series(km_paces)
    cv = (paces.std() / paces.mean()) * 100
    return round(cv, 2)


def save_run_analysis(db_path, filename, data):
    """통합 분석 결과를 run_analysis 테이블에 저장"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS run_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE NOT NULL,
        activity_date DATE,
        total_distance_km REAL,
        total_duration_sec INTEGER,
        avg_hr REAL,
        max_hr REAL,
        avg_cadence REAL,
        hr_drift_percent REAL,
        pace_stability_cv REAL,
        zone2_seconds INTEGER,
        zone2_ratio REAL,
        zone2_avg_speed_kmh REAL,
        zone2_avg_pace_min_km TEXT,
        analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cursor.execute('''INSERT OR REPLACE INTO run_analysis
        (filename, activity_date, total_distance_km, total_duration_sec,
         avg_hr, max_hr, avg_cadence, hr_drift_percent, pace_stability_cv,
         zone2_seconds, zone2_ratio, zone2_avg_speed_kmh, zone2_avg_pace_min_km, analyzed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (filename,
         data.get('activity_date'),
         data.get('total_distance_km'),
         data.get('total_duration_sec'),
         data.get('avg_hr'),
         data.get('max_hr'),
         data.get('avg_cadence'),
         data.get('hr_drift_percent'),
         data.get('pace_stability_cv'),
         data.get('zone2_seconds'),
         data.get('zone2_ratio'),
         data.get('zone2_avg_speed_kmh'),
         data.get('zone2_avg_pace_min_km'),
         datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logger.info(f"통합 분석 결과 DB에 저장: {filename}")


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
