# scripts/fit_analyzer.py
from fitparse import FitFile
import pandas as pd
import logging

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

def zone2_summary(df, hr_low=120, hr_high=140):
    if df.empty or 'heart_rate' not in df.columns:
        return {'zone2_seconds': 0, 'zone2_avg_speed': None}
    zone2 = df[(df['heart_rate'] >= hr_low) & (df['heart_rate'] <= hr_high)]
    if zone2.empty:
        return {'zone2_seconds': 0, 'zone2_avg_speed': None}
    avg_speed = zone2['speed'].mean() if 'speed' in zone2.columns else None
    return {
        'zone2_seconds': int(len(zone2)),
        'zone2_avg_speed': float(avg_speed) if avg_speed is not None else None
    }
