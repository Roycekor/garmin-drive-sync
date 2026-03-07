# Streamlit Community Cloud 배포 가이드

## 개요

`analysis.db`의 러닝 분석 데이터를 Streamlit 대시보드로 시각화하고, Streamlit Community Cloud에 무료 배포합니다.

---

## 배포용 레포지토리 구조

```
garmin-running-dashboard/
├── dashboard.py          # Streamlit 대시보드 앱
├── analysis.db           # 분석 결과 DB (로컬에서 생성)
├── requirements.txt      # streamlit, plotly, pandas
└── .gitignore
```

> 동기화/분석 스크립트는 포함하지 않습니다. `analysis.db`만 있으면 대시보드가 동작합니다.

---

## 1. 배포용 레포지토리 생성

```bash
mkdir garmin-running-dashboard
cd garmin-running-dashboard

# 대시보드 파일 복사
cp /path/to/garmin-drive-sync/dashboard.py .
cp /path/to/garmin-drive-sync/analysis.db .

# requirements.txt 생성
cat > requirements.txt << 'EOF'
streamlit>=1.30.0
plotly>=5.18.0
pandas>=2.2.0
EOF

# Git 초기화 및 커밋
git init
git add .
git commit -m "[init] add Streamlit running analytics dashboard"
```

## 2. GitHub에 Push

```bash
# GitHub에서 repo 생성 후
git remote add origin https://github.com/<username>/garmin-running-dashboard.git
git push -u origin main
```

## 3. Streamlit Community Cloud 배포

1. [share.streamlit.io](https://share.streamlit.io) 접속
2. GitHub 계정으로 로그인
3. **New app** 클릭
4. 설정 입력:
   - **Repository**: `<username>/garmin-running-dashboard`
   - **Branch**: `main`
   - **Main file path**: `dashboard.py`
5. **Deploy** 클릭
6. 배포 완료 시 `https://<app-name>.streamlit.app` URL 생성

---

## 데이터 업데이트

### 자동 복사 설정 (권장)

`garmin-drive-sync/config/dashboard.json`에 대시보드 저장소 경로를 설정하면, 분석 완료 시 `analysis.db`가 자동으로 복사됩니다:

```json
{
  "repo_path": "/path/to/garmin-running-dashboard"
}
```

대시보드 저장소에 git이 설정되어 있으면, 분석 완료 후 자동으로 `git add → commit → push`까지 수행합니다.
분석 실행만 하면 배포까지 자동으로 완료됩니다:

```bash
cd /path/to/garmin-drive-sync
python scripts/main.py --analyze-only
```

동작 흐름:

| 조건 | 동작 |
|------|------|
| `dashboard.json` 없음 | DB 복사 건너뜀 |
| 경로가 유효하지 않음 | 경고 로그, 건너뜀 |
| git repo 아님 | DB 복사만, push 건너뜀 |
| DB 변경 없음 | push 건너뜀 |
| DB 변경 있음 | 복사 → git add → commit → push |

### 수동 복사

설정 파일 없이 직접 복사할 수도 있습니다:

```bash
cp /path/to/garmin-drive-sync/analysis.db /path/to/garmin-running-dashboard/
cd /path/to/garmin-running-dashboard
git add analysis.db
git commit -m "[data] update analysis.db"
git push
```

Streamlit Cloud는 push 감지 시 자동으로 재배포합니다.

---

## 참고

- **무료 제한**: Streamlit Community Cloud는 퍼블릭 repo만 지원 (무료 플랜)
- **Sleep 모드**: 일정 기간 접속이 없으면 앱이 sleep 상태가 되며, 접속 시 자동으로 깨어남
- **데이터 고정**: `analysis.db`는 repo에 포함된 시점의 데이터가 표시됨 (실시간 동기화 아님)
