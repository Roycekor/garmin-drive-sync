import os
import sys
import logging
import asyncio
import queue
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.error import NetworkError
from telegram.ext import Application, CommandHandler, ContextTypes

# load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WORKDIR = Path(os.environ.get("WORKDIR", Path.home() / "garmin-drive-sync"))

# 봇 소유자 ID: 환경변수 TELEGRAM_OWNER_ID 우선, 없으면 파일에서 로드
OWNER_ID_FILE = WORKDIR / ".telegram_owner_id"
_ENV_OWNER_ID = os.environ.get("TELEGRAM_OWNER_ID")

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

# root logger → sync.log + console (main.py 로그 포함)
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(WORKDIR / "logs" / "sync.log"),
        logging.StreamHandler(),
    ],
)

# telegram bot 자체 로그 → telegram_bot.log (sync.log에는 미포함)
logger = logging.getLogger(__name__)
logger.propagate = False
_bot_handler = logging.FileHandler(WORKDIR / "logs" / "telegram_bot.log")
_bot_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logger.addHandler(_bot_handler)
logger.addHandler(logging.StreamHandler())

logging.getLogger("httpx").setLevel(logging.WARNING)

# Progress message batching interval (seconds)
PROGRESS_INTERVAL = 5


class QueueLogHandler(logging.Handler):
    """main.py logger -> thread-safe queue -> telegram message"""

    def __init__(self, msg_queue: queue.Queue):
        super().__init__(level=logging.INFO)
        self.msg_queue = msg_queue

    def emit(self, record):
        # garminconnect 내부 재시도(mobile+cffi 429 등)는 사용자 노이즈 — wrapper 로그만 노출
        if record.name.startswith("garminconnect"):
            return
        msg = record.getMessage()
        self.msg_queue.put(msg)


def load_owner_id():
    # 환경변수 우선
    if _ENV_OWNER_ID:
        try:
            return int(_ENV_OWNER_ID)
        except ValueError:
            logger.warning(f"TELEGRAM_OWNER_ID 환경변수 값이 유효하지 않음: {_ENV_OWNER_ID}")
    # 파일 fallback
    if OWNER_ID_FILE.exists():
        try:
            return int(OWNER_ID_FILE.read_text().strip())
        except (ValueError, OSError):
            logger.warning(f"OWNER_ID 파일 읽기 실패: {OWNER_ID_FILE}")
    return None


def save_owner_id(user_id: int):
    try:
        OWNER_ID_FILE.write_text(str(user_id))
    except OSError as e:
        logger.error(f"OWNER_ID 파일 저장 실패: {e}")
        raise


OWNER_ID = load_owner_id()

HELP_TEXT = (
    "/sync - Garmin sync + Drive upload\n"
    "/analyze - FIT file analysis only\n"
    "/status - Show last sync log\n"
    "/help - Show this help message"
)


def is_owner(update: Update) -> bool:
    if OWNER_ID is None:
        return False
    return update.effective_user.id == OWNER_ID


def _escape_markdown(text: str) -> str:
    """Markdown code block 안에서 백틱을 이스케이프"""
    return text.replace("`", "'")


async def _send_log_message(bot, chat_id, text: str):
    """로그 텍스트를 Telegram으로 전송 (Markdown 실패 시 plain text fallback)"""
    safe = _escape_markdown(text[:4000])
    try:
        await bot.send_message(chat_id=chat_id, text=f"```\n{safe}\n```", parse_mode="Markdown")
    except Exception:
        try:
            await bot.send_message(chat_id=chat_id, text=safe)
        except Exception:
            pass


async def send_progress(chat_id, bot, msg_queue: queue.Queue, done_event: asyncio.Event):
    """Drain queue and send batched progress messages to telegram."""
    while not done_event.is_set():
        await asyncio.sleep(PROGRESS_INTERVAL)
        lines = _drain_queue(msg_queue)
        if lines:
            await _send_log_message(bot, chat_id, "\n".join(lines))
    # flush remaining messages after task completes
    lines = _drain_queue(msg_queue)
    if lines:
        await _send_log_message(bot, chat_id, "\n".join(lines))


def _drain_queue(msg_queue: queue.Queue) -> list[str]:
    lines = []
    while True:
        try:
            lines.append(msg_queue.get_nowait())
        except queue.Empty:
            break
    return lines


async def run_with_progress(update, context, task_name, func):
    """Run func in executor while streaming logs to telegram."""
    chat_id = update.effective_chat.id
    bot = context.bot

    msg_queue = queue.Queue()
    handler = QueueLogHandler(msg_queue)

    # attach handler to main.py's logger (root logger captures all)
    main_logger = logging.getLogger()
    main_logger.addHandler(handler)

    done_event = asyncio.Event()
    progress_task = asyncio.create_task(send_progress(chat_id, bot, msg_queue, done_event))

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, func)
        done_event.set()
        await progress_task
        await update.message.reply_text(f"{task_name} completed.")
    except Exception as e:
        done_event.set()
        await progress_task
        logger.exception(f"{task_name} failed")
        await update.message.reply_text(f"{task_name} failed: {e}")
    finally:
        main_logger.removeHandler(handler)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global OWNER_ID
    user = update.effective_user
    if OWNER_ID is None:
        OWNER_ID = user.id
        save_owner_id(user.id)
        logger.info(f"Owner registered: {user.username} (id={user.id})")
        await update.message.reply_text(
            f"Garmin Sync Bot ready.\n"
            f"Owner: {user.username}\n\n"
            f"{HELP_TEXT}"
        )
    elif is_owner(update):
        await update.message.reply_text(HELP_TEXT)
    else:
        await update.message.reply_text("Not authorized.")


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    await update.message.reply_text("Sync started...")
    try:
        from main import run_once
    except ImportError as e:
        await update.message.reply_text(f"Import error: {e}")
        return

    await run_with_progress(update, context, "Sync", run_once)


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    await update.message.reply_text("Analysis started...")
    try:
        from main import analyze_local_files
    except ImportError as e:
        await update.message.reply_text(f"Import error: {e}")
        return

    await run_with_progress(update, context, "Analysis", analyze_local_files)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    await update.message.reply_text(HELP_TEXT)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    log_file = WORKDIR / "logs" / "sync.log"
    if not log_file.exists():
        await update.message.reply_text("No sync log found.")
        return

    from collections import deque
    with open(log_file, "r") as f:
        tail_lines = deque(f, maxlen=30)
    tail = "".join(tail_lines).strip()
    if len(tail) > 4000:
        tail = tail[-4000:]
    await _send_log_message(context.bot, update.effective_chat.id, tail)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """일시적 네트워크 에러는 WARNING, 그 외는 ERROR로 분류"""
    err = context.error
    if isinstance(err, NetworkError):
        logger.warning(f"네트워크 일시 오류 (자동 재시도됨): {err}")
    else:
        logger.error(f"예상치 못한 에러: {err}", exc_info=err)


def main():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_error_handler(error_handler)

    logger.info("Telegram bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
