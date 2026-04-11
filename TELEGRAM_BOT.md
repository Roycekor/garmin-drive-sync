# Telegram Bot

Garmin Sync 파이프라인을 텔레그램 봇으로 원격 실행할 수 있습니다.

---

## 설정

### 1. BotFather에서 봇 생성

1. 텔레그램에서 **@BotFather** 검색 → 대화 시작
2. `/newbot` 입력
3. 봇 이름과 username 입력 (username은 `_bot`으로 끝나야 함)
4. 발급된 토큰 복사

### 2. 환경변수 설정

`.env` 파일에 토큰과 소유자 ID 추가:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_OWNER_ID=your_telegram_user_id
```

> `TELEGRAM_OWNER_ID`를 모르면 비워두고 봇을 시작한 뒤 `/start`를 보내면 본인의 user ID가 안내됩니다.

---

## 실행

봇은 polling 방식으로 동작하므로 프로세스가 계속 실행되어야 합니다.

```bash
source venv/bin/activate
python scripts/telegram_bot.py
```

> 포그라운드에서 실행됩니다. 터미널을 닫으면 봇도 종료됩니다.

### 터미널 종료 후에도 유지

```bash
nohup python scripts/telegram_bot.py > /dev/null 2>&1 &
```

### macOS 재시작 시에도 자동 실행 (launchd)

```bash
# 1. 샘플 파일 복사
cp launch_agents/com.user.telegram-bot.plist.example launch_agents/com.user.telegram-bot.plist

# 2. 플레이스홀더를 실제 경로로 치환
sed -i '' "s|/path/to/garmin-drive-sync|$(pwd)|g" launch_agents/com.user.telegram-bot.plist
sed -i '' "s|/Users/your-username|$HOME|g" launch_agents/com.user.telegram-bot.plist

# 3. 로그 디렉토리 생성
mkdir -p ~/Library/Logs/telegram-bot

# 4. LaunchAgents에 등록
cp launch_agents/com.user.telegram-bot.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.telegram-bot.plist
```

`KeepAlive`가 설정되어 있어 프로세스가 종료되면 자동으로 재시작됩니다.

#### 서비스 관리

```bash
# 상태 확인
launchctl print gui/$(id -u)/com.user.telegram-bot

# 재시작
launchctl kickstart -k gui/$(id -u)/com.user.telegram-bot

# 중지
launchctl bootout gui/$(id -u)/com.user.telegram-bot
```

#### macOS TCC 권한 관련 주의사항

플레이스홀더 그대로 plist를 만들면 다음 문제를 겪을 수 있습니다:

1. **`exit code 78 (EX_CONFIG)`** — `~/Downloads` 등 macOS TCC가 보호하는 폴더 안에 stdout/stderr 로그 파일을 두면 launchd가 파일을 열지 못해 spawn이 실패합니다. 로그는 반드시 `~/Library/Logs/` 하위에 두세요.
2. **venv python 코드 서명 없음** — Homebrew/pyenv 기반 venv 바이너리는 코드 서명이 없어 launchd가 직접 실행을 거부할 수 있습니다. 샘플 plist는 `/bin/bash -c`로 래핑해 우회합니다.
3. **상대 경로 해석 실패** — `WorkingDirectory`를 `~/`로 두기 때문에 `settings.yaml`의 `config/client_secrets.json` 같은 상대 경로가 깨집니다. 샘플 plist는 bash 래퍼 안에서 `cd <project> && exec python ...` 형태로 실제 cwd를 프로젝트 루트로 고정합니다.

#### 로그 위치 (launchd 실행 시)

- launchd stdout/stderr: `~/Library/Logs/telegram-bot/stdout.log`, `stderr.log`
- 봇/sync 애플리케이션 로그: `logs/telegram_bot.log`, `logs/sync.log` (프로젝트 폴더 내)

---

## 봇 명령어

| 명령 | 동작 |
|------|------|
| `/start` | 봇 등록 (최초 1회 owner 설정) / 도움말 표시 |
| `/sync` | Garmin 동기화 + Google Drive 업로드 |
| `/analyze` | 로컬 FIT 파일 분석만 실행 |
| `/status` | 최근 sync 로그 15줄 확인 |
| `/help` | 사용 가능한 명령어 목록 확인 |

---

## 보안

- **Owner 결정 순서**: `TELEGRAM_OWNER_ID` 환경변수 → `.telegram_owner_id` 파일 → 첫 `/start` 유저 자동 등록
- 환경변수로 지정하면 자동 등록이 비활성화되어 가장 안전합니다.
- 환경변수 없이 사용하면 최초 `/start`를 보낸 유저가 owner로 등록되고 파일에 저장됩니다.
- Owner가 아닌 유저의 명령은 무시됩니다.
- Owner를 재설정하려면 `.telegram_owner_id` 파일을 삭제 후 봇을 재시작하세요.

---

## 로그

봇 실행 로그는 `logs/telegram_bot.log`에 기록됩니다.
