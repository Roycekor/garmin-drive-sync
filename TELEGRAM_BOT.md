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

`.env` 파일에 토큰 추가:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

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

# 2. /path/to/garmin-drive-sync를 실제 프로젝트 절대경로로 수정
sed -i '' "s|/path/to/garmin-drive-sync|$(pwd)|g" launch_agents/com.user.telegram-bot.plist

# 3. LaunchAgents에 등록
cp launch_agents/com.user.telegram-bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.telegram-bot.plist
```

`KeepAlive`가 설정되어 있어 프로세스가 종료되면 자동으로 재시작됩니다.

---

## 봇 명령어

| 명령 | 동작 |
|------|------|
| `/start` | 봇 등록 (최초 1회, owner 설정) |
| `/sync` | Garmin 동기화 + Google Drive 업로드 |
| `/analyze` | 로컬 FIT 파일 분석만 실행 |
| `/status` | 최근 sync 로그 15줄 확인 |
| `/help` | 사용 가능한 명령어 목록 확인 |

---

## 보안

- **Owner 등록**: 최초 `/start`를 보낸 유저가 owner로 등록됩니다.
- Owner 정보는 `.telegram_owner_id` 파일에 저장되며, `.gitignore`에 포함되어 있습니다.
- Owner가 아닌 유저의 명령은 무시됩니다.
- Owner를 재설정하려면 `.telegram_owner_id` 파일을 삭제 후 봇을 재시작하세요.

---

## 로그

봇 실행 로그는 `logs/telegram_bot.log`에 기록됩니다.
