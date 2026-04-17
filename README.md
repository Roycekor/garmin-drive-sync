# garmin-drive-sync

macOS에서 Garmin 러닝 활동을 자동으로 다운로드해 Google Drive에 백업하고, Zone2 트레이닝 분석 대시보드를 제공하는 파이프라인입니다.

---

## 주요 기능

- **Garmin Connect 자동 동기화** — FIT 파일 다운로드 → Google Drive 업로드
- **러닝 분석 대시보드** — Zone2 페이스 추이, HR drift, 주간거리, 페이스 안정성
- **중복 방지** — 업로드한 활동 ID를 로컬에 기록하여 재업로드 방지
- **자동 실행** — macOS launchd로 정기 동기화 가능
- **Telegram Bot** — 텔레그램에서 동기화/분석을 원격 실행

---

## 프로젝트 구조

```
garmin-drive-sync/
├─ scripts/
│  ├─ main.py              # 진입점 (동기화 + 분석)
│  ├─ garmin_client.py     # Garmin Connect 연동
│  ├─ drive_uploader.py    # Google Drive 업로드
│  ├─ fit_analyzer.py      # FIT 파일 분석 (Zone2, HR drift, 페이스 안정성)
│  └─ telegram_bot.py      # Telegram 봇 (원격 실행)
├─ config/
│  ├─ client_secrets.json  # Google OAuth 클라이언트 설정
│  └─ dashboard.json       # 대시보드 저장소 경로 설정
├─ dashboard.py            # Streamlit 대시보드
├─ analysis.db             # 분석 결과 DB (자동 생성)
├─ requirements.txt
├─ settings.yaml           # PyDrive2 OAuth 설정
├─ INSTALL.md              # 설치 및 설정 가이드
├─ DASHBOARD.md            # 대시보드 배포 가이드
└─ launch_agents/          # macOS launchd 설정
```

---

## 빠른 시작

> 처음 설정하는 경우 [INSTALL.md](INSTALL.md)를 먼저 참고하세요.

### 동기화 실행

```bash
source venv/bin/activate
python scripts/main.py
```

| 모드 | 조건 | 동작 |
|------|------|------|
| 초기 동기화 | 첫 실행 (`.sync_initialized` 없음) | 모든 과거 활동 다운로드 + 업로드 |
| 정기 동기화 | 이후 실행 | 최근 20개 활동만 조회, 새 활동만 업로드 |

### CLI 옵션

```bash
python scripts/main.py [옵션]
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--analyze-only` | Garmin 다운로드/업로드 건너뛰고 로컬 FIT 파일만 분석 | - |
| `--count N` | 정기 동기화 시 가져올 최근 활동 수 | 20 |
| `--reanalyze` | 마커 파일 무시, 모든 FIT 파일 재분석 | - |
| `--verbose`, `-v` | DEBUG 레벨 로깅 활성화 | - |

### 사용 예시

```bash
# 기본 동기화 (최근 20개 활동)
python scripts/main.py

# 최근 50개 활동 동기화
python scripts/main.py --count 50

# 로컬 FIT 파일만 분석 (신규 파일만)
python scripts/main.py --analyze-only

# 분석 로직/파라미터 변경 후 전체 재분석
python scripts/main.py --analyze-only --reanalyze

# 디버그 로그 확인
python scripts/main.py --analyze-only -v
```

### FIT 파일 분석

로컬 `tmp/` 폴더의 FIT 파일을 분석하여 `analysis.db`에 저장합니다.
`config/dashboard.json`에 대시보드 저장소 경로가 설정되어 있으면, 분석 완료 후 `analysis.db`를 자동으로 복사합니다.

기본적으로 마커 파일(`.analyze_marker`) 이후에 추가된 신규 파일만 분석합니다. 분석 로직이나 파라미터를 변경한 경우 `--reanalyze`로 전체 재분석이 필요합니다.

### 대시보드 실행

```bash
streamlit run dashboard.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

---

## 분석 대상 데이터

### 분석 필터
- FIT 파일의 `sport` 필드가 **running**인 활동만 분석 대상
- 비러닝 활동(cycling, walking, strength_training 등)은 자동 제외

### 분석 지표

| 지표 | 설명 | 기준 |
|------|------|------|
| **Zone2 Pace** | 심박수 137-156 bpm 구간의 평균 페이스 | 낮을수록 좋음 (속도 향상) |
| **HR Drift** | 전반부/후반부 평균 심박수 변화율 | < 5% 양호, > 7% 주의 |
| **Weekly Distance** | 주간 총 러닝 거리 | 훈련량 모니터링 |
| **Pace Stability** | 8km+ 장거리 런의 1km 구간별 페이스 변동계수(CV) | < 7.5% 안정 |

### 설정 변경

Zone2 심박수 범위와 장거리 기준 거리는 `scripts/fit_analyzer.py`에서 수정할 수 있습니다:

```python
# Zone2 심박수 범위 (기본값: 137-156 bpm)
def zone2_summary(df, hr_low=137, hr_high=156):

# 장거리 페이스 안정성 분석 기준 거리 (기본값: 8km)
def pace_stability(df, min_distance_km=8):
```

변경 후 전체 재분석이 필요합니다:
```bash
python scripts/main.py --analyze-only --reanalyze
```

### DB 스키마 (`run_analysis` 테이블)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `activity_date` | DATE | 활동 날짜 |
| `total_distance_km` | REAL | 총 거리 (km) |
| `total_duration_sec` | INTEGER | 총 시간 (초) |
| `avg_hr` | REAL | 평균 심박수 |
| `max_hr` | REAL | 최대 심박수 |
| `avg_cadence` | REAL | 평균 케이던스 |
| `hr_drift_percent` | REAL | HR drift (%) |
| `pace_stability_cv` | REAL | 페이스 변동계수 (%) |
| `zone2_seconds` | INTEGER | Zone2 구간 시간 (초) |
| `zone2_avg_speed_kmh` | REAL | Zone2 평균 속도 (km/h) |
| `zone2_avg_pace_min_km` | TEXT | Zone2 평균 페이스 (min/km) |

### DB 조회 예시

```bash
# Zone2 페이스 추이
sqlite3 analysis.db "SELECT activity_date, zone2_avg_pace_min_km, hr_drift_percent FROM run_analysis ORDER BY activity_date"

# 8km+ 장거리 런 페이스 안정성
sqlite3 analysis.db "SELECT activity_date, total_distance_km, pace_stability_cv FROM run_analysis WHERE pace_stability_cv IS NOT NULL ORDER BY activity_date"

# 주간 거리 합산
sqlite3 analysis.db "SELECT strftime('%Y-W%W', activity_date) as week, ROUND(SUM(total_distance_km),1) as km FROM run_analysis GROUP BY week ORDER BY week"
```

---

## 대시보드

Streamlit 기반 인터랙티브 대시보드로 4개 차트를 제공합니다:

1. **Zone2 Pace Trend** — 5회 이동평균 추세선 포함, 페이스 개선 추이 확인
2. **HR Drift** — 색상 코딩 (초록 ≤5%, 주황 5-7%, 빨강 >7%)
3. **Weekly Distance** — 주간 총 거리 bar chart
4. **Long Run Pace Stability (8km+)** — 변동계수 7.5% 기준선 표시

사이드바에서 날짜 범위 및 최소 거리 필터를 조절할 수 있습니다.

### 대시보드 배포

Streamlit Community Cloud에 무료 배포할 수 있습니다. 자세한 내용은 [DASHBOARD.md](DASHBOARD.md)를 참고하세요.

### 대시보드 저장소 자동 동기화

`config/dashboard.json`에 배포용 저장소 경로를 설정하면, 분석 완료 시 `analysis.db`가 자동으로 복사됩니다:

```json
{
  "repo_path": "/path/to/garmin-running-dashboard"
}
```

설정 파일이 없거나 경로가 유효하지 않으면 복사를 건너뜁니다.

---

## 운영 (Operations)

### Telegram Bot (launchd)

텔레그램 봇은 macOS launchd 서비스로 상시 구동됩니다.

```bash
# 상태 확인
launchctl print gui/$(id -u)/com.user.telegram-bot

# 재시작
launchctl kickstart -k gui/$(id -u)/com.user.telegram-bot

# 중지
launchctl bootout gui/$(id -u)/com.user.telegram-bot

# 시작 (중지 후)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.telegram-bot.plist
```

- Plist: `~/Library/LaunchAgents/com.user.telegram-bot.plist`
- 로그: `~/Library/Logs/telegram-bot/stderr.log`, `~/Library/Logs/telegram-bot/stdout.log`

---

## Google Drive 업로드 구조

```
Google Drive
└─ Garmin/
   ├─ Run/
   │  └─ {YYYY}/
   │     └─ activity_{ID}_{DATE}.fit
   ├─ Bike/
   ├─ Swim/
   └─ ...
```

활동 타입별로 자동 분류됩니다: Run, Bike, Swim, Trail, Hike, Walk, Strength, Yoga 등.

---

## 기술 스택

| 패키지 | 용도 |
|--------|------|
| `garminconnect` | Garmin Connect API |
| `PyDrive2` | Google Drive 업로드 |
| `fitparse` | FIT 파일 파싱 |
| `pandas` | 데이터 처리 |
| `streamlit` | 대시보드 UI |
| `plotly` | 인터랙티브 차트 |
| `python-telegram-bot` | Telegram 봇 |

---

## 라이선스

MIT License
