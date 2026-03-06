# 설치 및 설정 가이드

## 목차

1. [준비물](#준비물)
2. [프로젝트 설정](#프로젝트-설정)
3. [Google Drive API 설정](#google-drive-api-설정)
4. [.env 파일 설정](#env-파일-설정)
5. [초기 실행](#초기-실행)
6. [macOS launchd 자동 실행 설정](#macos-launchd-자동-실행-설정)
7. [보안 권장사항](#보안-권장사항)
8. [문제 발생 시 확인 포인트](#문제-발생-시-확인-포인트)

---

## 준비물

- **macOS** (항상 켜져 있는 머신 권장)
- **Python 3.13+** (venv 사용 권장)
- **Garmin Connect 계정** (이메일/비밀번호)
- **Google 계정** + Google Drive API 설정

---

## 프로젝트 설정

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

---

## Google Drive API 설정

### 1. Google Cloud Console 접속 및 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속합니다
2. 상단의 **프로젝트 선택** 드롭다운 클릭
3. **새 프로젝트** 선택
   - 프로젝트명: `garmin-drive-sync` (또는 선호하는 이름)
   - 만들기를 클릭하여 프로젝트 생성

### 2. Google Drive API 활성화

1. 생성된 프로젝트가 선택되면, 좌측 메뉴에서 **API 및 서비스** 클릭
2. **라이브러리** 선택
3. 검색창에 "Google Drive API" 입력
4. 검색 결과에서 **Google Drive API** 클릭
5. **사용 설정** (또는 **Enable**) 버튼 클릭

### 3. OAuth 동의 화면 구성

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

### 4. OAuth Client ID 생성

1. **API 및 서비스** → **사용자 인증 정보** 클릭
2. **+ 사용자 인증 정보 만들기** → **OAuth 클라이언트 ID** 선택
3. 애플리케이션 유형: **데스크톱 앱** (Desktop application) 선택
4. 이름: `garmin-drive-sync`
5. **만들기** 버튼 클릭
6. **JSON 다운로드** 버튼을 클릭하여 `client_secrets.json` 파일 다운로드

### 5. 파일 배치

```bash
cp ~/Downloads/client_secrets.json ./config/client_secrets.json

# 확인
ls -la config/client_secrets.json
```

---

## .env 파일 설정

프로젝트 루트에 `.env` 파일을 생성합니다:

```bash
GARMIN_EMAIL=your_garmin_email@example.com
GARMIN_PASSWORD=your_garmin_password
GARMIN_MFA_TOKEN=your_mfa_token_if_needed
DRIVE_PARENT_FOLDER_ID=your_google_drive_folder_id
UPLOAD_PATH=Garmin/Run
SYNC_INTERVAL=3600
LOG_LEVEL=INFO
```

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

---

## 초기 실행

```bash
source venv/bin/activate
python scripts/main.py
```

> **첫 실행 시 주의**: Google OAuth 인증을 위해 브라우저 창이 열릴 수 있습니다. 인증을 완료하면 `credentials.json`이 자동 생성됩니다.

### 초기화 모드 (첫 실행)

첫 실행 시 자동으로 모든 과거 데이터를 동기화합니다:
- 첫 실행 감지 → 모든 과거 Garmin 활동 다운로드
- 초기 동기화 완료 → `.sync_initialized` 파일 생성
- 다음부터 자동으로 정기 모드로 전환

### 정기 동기화 모드 (두 번째 실행 이후)

- `.sync_initialized` 감지 → 최근 20개 활동만 조회
- 새로운 활동만 업로드, 기존 활동은 건너뜀

### 동기화 초기화 (다시 모든 데이터 받기)

```bash
rm .sync_initialized
python scripts/main.py
```

---

## macOS launchd 자동 실행 설정

### 1단계: plist 파일 수정

```bash
cp launch_agents/com.user.garmin-sync.plist.example launch_agents/com.user.garmin-sync.plist
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
cp launch_agents/com.user.garmin-sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.garmin-sync.plist
```

### 3단계: 실행 간격 설정

plist 파일의 `<key>StartInterval</key>` 값을 조정합니다 (초 단위):
- 30분: `1800`
- 1시간: `3600`
- 6시간: `21600`
- 24시간: `86400`

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
```

---

## 보안 권장사항

1. **Garmin 비밀번호**: `.env` 파일에만 저장하고, 리포지토리에 절대 올리지 마세요.
2. **Google OAuth 토큰**: `credentials.json`은 자동 생성되며 로컬에만 보관합니다.
3. **GitHub에 업로드 시**:
   - `.env`, `config/client_secrets.json`, `credentials.json`은 제외
   - 올릴 파일: `README.md`, `requirements.txt`, `scripts/`, `settings.yaml`, `launch_agents/`

---

## 문제 발생 시 확인 포인트

### Garmin 로그인 실패
- `.env`의 이메일/비밀번호 확인
- 비밀번호에 특수문자가 있으면 따옴표로 감싸기
- MFA가 활성화되어 있으면 `GARMIN_MFA_TOKEN` 설정

### Google Drive 인증 실패
- `config/client_secrets.json`이 올바른 경로에 있는지 확인
- `credentials.json` 삭제 후 다시 실행하면 브라우저 인증 재시도
- 권한 거부 시 "고급" → "앱 허용" 클릭

### 중복 파일 업로드
- `uploaded.json`에서 활동 ID 기록 확인
- 이전 업로드 기록이 손상되었으면 파일 재설정

### launchd 작동 안 함
- plist 파일의 경로 확인 (절대경로 필요)
- 문법 오류: `plutil -lint` 명령으로 확인
- 상태 확인: `launchctl list | grep garmin-sync`

### 수동 디버깅

```bash
LOG_LEVEL=DEBUG python scripts/main.py
```
