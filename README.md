# garmin-drive-sync

macOS에서 **Garmin 활동을 자동으로 다운로드해 Google Drive에 업로드**하고 기본 Zone2 분석을 수행하는 로컬 파이프라인 템플릿입니다. `.env`로 환경변수를 관리하고, `launchd`로 정기 실행하도록 구성되어 있습니다.

---

## 목차

1. [개요](#개요)
2. [프로젝트 파일 구조](#프로젝트-파일-구조)
3. [준비물](#준비물)
4. [설치 및 초기 실행](#설치-및-초기-실행)
5. [활동 데이터 로드 모드](#활동-데이터-로드-모드)
6. [.env 설정](#env-설정)
7. [파일 설명](#파일-설명)
8. [macOS launchd(자동 실행) 설정](#macos-launchd자동-실행-설정)
9. [Google Drive 업로드 경로 구조](#google-drive-업로드-경로-구조)
10. [보안 권장사항](#보안-권장사항)
11. [문제 발생 시 확인 포인트](#문제-발생-시-확인-포인트)

---

## 개요

이 템플릿은 macOS 로컬(항상 켜진 맥)에서 동작하도록 설계된 파이프라인입니다. 주요 동작은 다음과 같습니다.

- **Garmin Connect에서 최근 활동 가져오기** - 자동으로 Garmin 계정에 접속
- **FIT 파일 다운로드** - 각 활동을 `.fit` 파일 형식으로 다운로드
- **Google Drive에 업로드** - `Garmin/Run/{YYYY}/` 폴더를 자동 생성하고 파일 업로드
- **FIT 분석** - 파일을 파싱해 간단한 Zone2(심박 범위) 요약 로그 출력
- **중복 방지** - 업로드한 활동 ID는 로컬에 저장하여 중복 업로드 방지

모든 설정은 `.env`로 관리합니다.

---

## 프로젝트 파일 구조

```
garmin-drive-sync/
├─ README.md
├─ requirements.txt
├─ settings.yaml
├─ config/
│  └─ client_secrets.json   # Google OAuth 파일 (직접 다운로드 필요)
├─ scripts/
│  ├─ main.py              # 진입점
│  ├─ garmin_client.py     # Garmin 연동 로직
│  ├─ drive_uploader.py    # Google Drive 업로드 로직
│  └─ fit_analyzer.py      # FIT 파일 분석
├─ credentials.json         # Google OAuth 토큰 (자동 생성)
└─ launch_agents/
   └─ com.user.garmin-sync.plist.example   # launchd 설정 파일
```

---

## 준비물

- **macOS** (항상 켜져 있는 머신 권장)
- **Python 3.13+** (venv 사용 권장)
- **Garmin Connect 계정** (이메일/비밀번호)
- **Google 계정** + Google Drive API 설정
  - [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
  - Drive API 활성화
  - OAuth Client ID (Desktop) 생성 후 `config/client_secrets.json`로 저장

---

## 설치 및 초기 실행

### 1단계: 프로젝트 설정

```bash
# 프로젝트 폴더 생성 (이미 있다면 건너뜀)
mkdir -p ~/garmin-drive-sync
cd ~/garmin-drive-sync

# 가상환경 생성 및 활성화
python3.13 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install --upgrade pip
pip install -r requirements.txt
```

### 2단계: Google Drive API 설정

이 섹션에서는 Google Cloud Console에서 Google Drive API를 활성화하고 OAuth 인증 정보를 생성합니다.

#### 2-1. Google Cloud Console 접속 및 프로젝트 선택

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속합니다
2. 상단의 **프로젝트 선택** 드롭다운 클릭
3. **새 프로젝트** 선택
   - 프로젝트명: `garmin-drive-sync` (또는 선호하는 이름)
   - 만들기를 클릭하여 프로젝트 생성

#### 2-2. Google Drive API 활성화

1. 생성된 프로젝트가 선택되면, 좌측 메뉴에서 **API 및 서비스** 클릭
2. **라이브러리** 선택
3. 검색창에 "Google Drive API" 입력
4. 검색 결과에서 **Google Drive API** 클릭
5. **사용 설정** (또는 **Enable**) 버튼 클릭
   - API가 활성화될 때까지 잠시 기다립니다

#### 2-3. OAuth 동의 화면 구성

1. **API 및 서비스** → **OAuth 동의 화면** 클릭
2. **User Type** 선택
   - 개인 사용: **외부** 선택
   - 회사 사용: **내부** 선택 (선택 사항)
3. **만들기** 버튼 클릭
4. 필수 필드 입력:
   - **앱 이름**: `garmin-drive-sync`
   - **사용자 지원 이메일**: 본인의 Google 계정 이메일
   - **개발자 연락처 정보**: 본인의 이메일
5. **저장 및 계속** 클릭
6. 범위 추가 페이지에서 **범위 추가** 클릭
   - `https://www.googleapis.com/auth/drive.file` 검색 및 선택
   - **업데이트** 클릭
7. **저장 및 계속** → **완료** 클릭

#### 2-4. 사용자 인증 정보(OAuth Client ID) 생성

1. **API 및 서비스** → **사용자 인증 정보** 클릭
2. **+ 사용자 인증 정보 만들기** → **OAuth 클라이언트 ID** 선택
3. 애플리케이션 유형 선택:
   - **애플리케이션 유형**: **데스크톱 앱** (Desktop application) 선택
   - **이름**: `garmin-drive-sync` (또는 원하는 이름)
4. **만들기** 버튼 클릭
5. 생성된 **클라이언트 ID** 및 **클라이언트 보안 비밀** 창이 표시됩니다
6. **JSON 다운로드** 버튼을 클릭하여 `client_secrets.json` 파일 다운로드

#### 2-5. 파일 배치

다운로드한 `client_secrets.json` 파일을 프로젝트의 `config/` 폴더에 배치합니다:

```bash
# 파일 복사
cp ~/Downloads/client_secrets.json ./config/client_secrets.json

# 또는 Finder에서 드래그 앤 드롭
```

**확인**:
```bash
ls -la config/client_secrets.json
```

파일이 정상적으로 배치되었으면 다음 단계로 진행합니다.

### 3단계: .env 파일 설정

프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 추가합니다. (자세한 설정은 [.env 설정](#env-설정) 섹션 참고)

```bash
GARMIN_EMAIL=your_garmin_email@example.com
GARMIN_PASSWORD=your_garmin_password
GARMIN_MFA_TOKEN=your_mfa_token_if_needed
DRIVE_PARENT_FOLDER_ID=your_google_drive_folder_id
UPLOAD_PATH=Garmin/Run
SYNC_INTERVAL=3600
```

### 4단계: 초기 실행

```bash
source venv/bin/activate
python scripts/main.py
```

> **첫 실행 시 주의**: Google OAuth 인증을 위해 브라우저 창이 열릴 수 있습니다. 인증을 완료하면 `credentials.json`이 자동 생성됩니다.

#### 4-1. 자동 초기화 모드 (첫 실행)

**첫 실행 시 이 스크립트는 자동으로 모든 과거 데이터를 동기화합니다:**

```bash
source venv/bin/activate
python scripts/main.py
```

**동작:**
- 🔄 첫 실행 감지 → 모든 과거 Garmin 활동 다운로드 (`list_all_activities()`)
- 📊 각 활동마다 진행상황 출력 (예: `[1/250] 활동 12345: ✅ 업로드 완료`)
- ✅ 초기 동기화 완료 → `.sync_initialized` 파일 생성
- 다음부터 변경 없이 같은 명령 사용 가능 (자동으로 정기 모드로 전환)

**초기 동기화 소요 시간:**
- 100-200개 활동: 약 10-20분
- 200개 이상: 30분 이상 소요 가능

#### 4-2. 정기 동기화 모드 (두 번째 실행 이후)

초기 동기화 완료 후 같은 명령으로 실행하면 **자동으로 정기 모드로 전환**됩니다:

```bash
source venv/bin/activate
python scripts/main.py
```

**동작:**
- 📊 `.sync_initialized` 파일 감지 → 최근 20개 활동만 다운로드 (`list_recent_activities(limit=20)`)
- ⚡ 실행 시간 단축 (약 30초-1분)
- 🔔 새로운 활동만 업로드, 기존 활동은 건너뜀

#### 4-3. 동기화 초기화 (다시 모든 데이터 받기)

만약 다시 모든 과거 데이터를 동기화하려면:

```bash
# 초기화 파일 삭제
rm .sync_initialized

# 다시 실행
python scripts/main.py
```

---

## 활동 데이터 로드 모드

이 프로젝트는 **자동 이중 모드 동기화**를 지원합니다:

| 단계 | 모드 | 데이터 범위 | 소요 시간 | 자동 전환 |
|------|------|-----------|---------|---------|
| **1차** | 초기 동기화 | 모든 과거 데이터 | 10-40분 | ✅ 자동 |
| **2차+** | 정기 동기화 | 최근 20개 활동 | 30초-1분 | ✅ 자동 |

**핵심 특징:**
- 코드 수정 불필요 → 자동으로 전환됨
- `.sync_initialized` 파일로 상태 관리
- 진행상황 실시간 로그 출력 (예: `[25/250] 활동 ID: ✅ 업로드 완료`)
- 업로드된 활동 중복 방지 자동화

## .env 설정

프로젝트 루트에 `.env` 파일을 생성하고 아래 환경변수를 설정합니다.

| 변수명 | 설명 | 예시 |
|--------|------|------|
| `GARMIN_EMAIL` | Garmin Connect 로그인 이메일 | `user@gmail.com` |
| `GARMIN_PASSWORD` | Garmin Connect 비밀번호 | `your_password` |
| `GARMIN_MFA_TOKEN` | (선택) MFA 토큰 | `123456` |
| `DRIVE_PARENT_FOLDER_ID` | Google Drive의 대상 폴더 ID | `1A2b3C4d5E...` |
| `UPLOAD_PATH` | Drive 내 업로드 폴더 경로 | `Garmin/Run` |
| `SYNC_INTERVAL` | 동기화 간격(초) | `3600` (1시간) |
| `LOG_LEVEL` | 로그 레벨 | `INFO` 또는 `DEBUG` |

### Google Drive 폴더 ID 확인하는 방법

1. Google Drive에서 대상 폴더 열기
2. URL에서 ID 복사: `https://drive.google.com/drive/folders/{FOLDER_ID}`
3. `{FOLDER_ID}`를 `.env`의 `DRIVE_PARENT_FOLDER_ID`에 붙여넣기

### 예시 .env 파일

```bash
GARMIN_EMAIL=myemail@gmail.com
GARMIN_PASSWORD=mysecurepassword
DRIVE_PARENT_FOLDER_ID=1A2b3C4d5E6f7G8h9I0j1K
UPLOAD_PATH=Garmin/Run
SYNC_INTERVAL=3600
LOG_LEVEL=INFO
```

---

## 파일 설명

### `scripts/main.py`
- **역할**: 프로젝트의 진입점
- **기능**: 설정 로드, Garmin 데이터 다운로드, Google Drive 업로드 조율
- **실행**: `python scripts/main.py`

### `scripts/garmin_client.py`
- **역할**: Garmin Connect 연결 및 활동 다운로드
- **주요 함수**:
  - `list_recent_activities(limit=20)` - 최근 N개 활동 목록 조회 (빠른 동기화용)
  - `list_all_activities(batch_size=100)` - 모든 과거 활동 목록 조회 (초기 대량 동기화용)
  - `download_activity_fit()` - FIT 파일 다운로드

### `scripts/drive_uploader.py`
- **역할**: Google Drive에 파일 업로드
- **주요 함수**:
  - `authenticate()` - Google Drive 인증
  - `upload_file()` - 파일 업로드
  - `create_folder_if_not_exists()` - 폴더 자동 생성

### `scripts/fit_analyzer.py`
- **역할**: FIT 파일 분석 및 통계 계산
- **주요 함수**:
  - `parse_fit()` - FIT 파일 파싱
  - `analyze_zone2()` - Zone2 심박 범위 분석
  - `get_summary()` - 활동 요약 정보

### `settings.yaml`
- **역할**: PyDrive2 설정
- **내용**: Google Drive API 클라이언트 설정, OAuth 범위 정의

### `requirements.txt`
- 필수 파이썬 패키지 목록
- 주요 패키지:
  - `garminconnect>=0.2.34` - Garmin API
  - `PyDrive2==1.21.3` - Google Drive API
  - `fitparse==1.2.0` - FIT 파일 파싱
  - `pandas>=2.2.0` - 데이터 처리

---

## macOS launchd(자동 실행) 설정

정기적으로 자동 실행하려면 macOS의 `launchd`를 사용합니다.

### 1단계: plist 파일 수정

`launch_agents/com.user.garmin-sync.plist.example`을 복사하여 `com.user.garmin-sync.plist`로 저장합니다.

```bash
cp launch_agents/com.user.garmin-sync.plist.example launch_agents/com.user.garmin-sync.plist
```

파일을 엽니다:

```bash
nano ~/Library/LaunchAgents/com.user.garmin-sync.plist
```

아래 부분을 자신의 환경에 맞게 수정합니다:

```xml
<key>Program</key>
<string>/Users/YOUR_USERNAME/garmin-drive-sync/venv/bin/python</string>

<key>ProgramArguments</key>
<array>
    <string>/Users/YOUR_USERNAME/garmin-drive-sync/venv/bin/python</string>
    <string>/Users/YOUR_USERNAME/garmin-drive-sync/scripts/main.py</string>
</array>

<key>WorkingDirectory</key>
<string>/Users/YOUR_USERNAME/garmin-drive-sync</string>

<key>EnvironmentVariables</key>
<dict>
    <key>PATH</key>
    <string>/Users/YOUR_USERNAME/garmin-drive-sync/venv/bin:/usr/local/bin:/usr/bin:/bin</string>
</dict>
```

> `YOUR_USERNAME`을 실제 macOS 사용자명으로 변경하세요. `whoami` 명령으로 확인 가능합니다.

### 2단계: plist 파일 등록

```bash
# plist 파일을 LaunchAgents 폴더에 복사
cp launch_agents/com.user.garmin-sync.plist ~/Library/LaunchAgents/

# launchd에 등록
launchctl load ~/Library/LaunchAgents/com.user.garmin-sync.plist
```

### 3단계: 실행 간격 설정

plist 파일의 `<key>StartInterval</key>` 값을 조정합니다. (초 단위)

```xml
<key>StartInterval</key>
<integer>3600</integer>  <!-- 1시간마다 실행 (3600초) -->
```

자주 사용하는 간격:
- 30분: `1800`
- 1시간: `3600`
- 6시간: `21600`
- 24시간: `86400`

### 4단계: 동작 확인

```bash
# launchd에서 작업 확인
launchctl list | grep garmin-sync

# 수동 실행 테스트
launchctl start com.user.garmin-sync

# 로그 확인
log stream --predicate 'process == "Python"'
```

### 관리 명령어

```bash
# 활성화
launchctl load ~/Library/LaunchAgents/com.user.garmin-sync.plist

# 비활성화
launchctl unload ~/Library/LaunchAgents/com.user.garmin-sync.plist

# 수동 실행
launchctl start com.user.garmin-sync

# 중지
launchctl stop com.user.garmin-sync

# 설정 재로드
launchctl unload ~/Library/LaunchAgents/com.user.garmin-sync.plist
launchctl load ~/Library/LaunchAgents/com.user.garmin-sync.plist
```

---

## Google Drive 업로드 경로 구조

파일은 다음의 구조로 자동 생성되어 업로드됩니다:

```
Google Drive
└─ Garmin/
   └─ Run/
      ├─ 2024/
      │  ├─ activity_123_2024-01-15.fit
      │  ├─ activity_124_2024-01-16.fit
      │  └─ ...
      ├─ 2025/
      │  ├─ activity_200_2025-01-10.fit
      │  └─ ...
      └─ 2026/
         ├─ activity_300_2026-01-01.fit
         └─ ...
```

각 파일명은 다음 형식을 따릅니다:

```
activity_{ACTIVITY_ID}_{DATE}.fit
```

파일명 예시:
- `activity_123_2024-01-15.fit`
- `activity_456_2025-06-20.fit`

---

## 보안 권장사항

### 필수: .gitignore 설정

Git에 민감한 파일이 실수로 업로드되지 않도록 `.gitignore`에 다음을 추가합니다:

```gitignore
# 환경 변수
.env
.env.local
.env.*.local

# Google OAuth 파일
config/client_secrets.json
credentials.json

# Python 가상환경
venv/
env/

# 로그 및 임시 파일
logs/
tmp/
*.log

# macOS
.DS_Store
*.bak

# IDE
.vscode/
.idea/
```

### 권장사항

1. **Garmin 비밀번호**: `.env` 파일에만 저장하고, 리포지토리에 절대 올리지 마세요.
2. **Google OAuth 토큰**: `credentials.json`은 자동 생성되며 로컬에만 보관합니다.
3. **GitHub에 업로드 시**: 
   - `.env`, `config/client_secrets.json`, `credentials.json`은 제외
   - 올릴 파일: `README.md`, `requirements.txt`, `scripts/`, `settings.yaml`, `launch_agents/`
4. **GitHub Actions 사용**:
   - Secrets 저장소에 `GARMIN_EMAIL`, `GARMIN_PASSWORD`, `DRIVE_PARENT_FOLDER_ID` 등 등록
   - 워크플로 파일에서 환경변수로 주입

---

## 문제 발생 시 확인 포인트

### 1. "Garmin 로그인 실패"

```bash
# .env 파일의 이메일과 비밀번호 확인
cat .env | grep GARMIN

# Garmin Connect 웹 로그인 시도하여 계정 상태 확인
```

**해결책**:
- 비밀번호에 특수문자가 있으면 `.env`에서 따옴표로 감싸기
- MFA가 활성화되어 있으면 `GARMIN_MFA_TOKEN` 설정

### 2. "Google Drive 인증 실패"

```bash
# credentials.json 파일 확인
ls -la credentials.json

# 파일이 없으면 수동으로 삭제하고 다시 실행
rm credentials.json
python scripts/main.py
```

**해결책**:
- `config/client_secrets.json`이 올바른 경로에 있는지 확인
- 첫 실행 시 브라우저에서 Google 계정 인증 완료
- 권한 거부 시 "고급" → "앱 허용" 클릭

### 3. "중복 파일 업로드"

```bash
# 로컬 저장된 활동 ID 확인
cat uploaded_activities.json  # 또는 유사한 로컬 저장 파일
```

**해결책**:
- 이전 업로드 기록이 손상되었으면 파일 재설정
- 수동으로 Google Drive에서 중복 파일 삭제

### 4. launchd 작동 안 함

```bash
# launchd 상태 확인
launchctl list | grep garmin-sync

# 상세 로그 확인
log stream --predicate 'process == "Python"' --level debug
```

**해결책**:
- plist 파일의 경로를 다시 확인 (절대경로 필요)
- 문법 오류는 `plutil -lint` 명령으로 확인
- 실행 권한 확인: `chmod +x ~/Library/LaunchAgents/com.user.garmin-sync.plist`

---



## 추가 옵션 및 팁

### 로그 파일 크기 관리

로그가 너무 커지지 않도록 주기적으로 정리합니다:

```bash
# 1주일 이상된 로그 삭제
find logs/ -name "*.log" -mtime +7 -delete
```

### 수동 디버깅 실행

```bash
# DEBUG 모드로 실행하여 상세 로그 출력
LOG_LEVEL=DEBUG python scripts/main.py
```

### FIT 파일 직접 분석

```bash
# 특정 FIT 파일 분석
python -c "
from scripts.fit_analyzer import parse_fit
data = parse_fit('path_to_file.fit')
print(data)
"
```

### 특정 활동만 다시 업로드

```python
# scripts/main.py 수정 또는 스크립트에서
# 업로드 이력 파일 수정하여 특정 활동 ID에 대한 재업로드 강제
```

---

## 라이선스

MIT License

---

## 참고 링크

- [Garmin Connect](https://connect.garmin.com/)
- [Google Drive API](https://developers.google.com/drive)
- [fitparse 라이브러리](https://github.com/polyvertex/fitparse)
- [PyDrive2 문서](https://docs.iterative.ai/PyDrive2/)

---

## 문의 및 피드백

문제가 발생하거나 개선 사항이 있으면 GitHub Issues를 통해 보고해주세요.

Happy syncing! 🏃‍♂️📊