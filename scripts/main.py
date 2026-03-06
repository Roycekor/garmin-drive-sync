# scripts/main.py
import os
import logging
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# load .env from project root
load_dotenv()

from garmin_client import GarminClient
from drive_uploader import DriveUploader
from fit_analyzer import fit_to_dataframe, zone2_summary

# 환경/경로 설정
GARMIN_USER = os.environ.get('GARMIN_USER')
GARMIN_PASS = os.environ.get('GARMIN_PASS')
DRIVE_PARENT_FOLDER_ID = os.environ.get('DRIVE_PARENT_FOLDER_ID')
WORKDIR = Path(os.environ.get('WORKDIR', Path.home() / "garmin-drive-sync"))
TMPDIR = WORKDIR / "tmp"
LOGFILE = WORKDIR / "logs/sync.log"
DBFILE = WORKDIR / "uploaded.json"

# 로깅 설정
LOGDIR = WORKDIR / "logs"
LOGDIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TMPDIR.mkdir(parents=True, exist_ok=True)

def load_uploaded():
    if DBFILE.exists():
        try:
            return set(json.loads(DBFILE.read_text()))
        except Exception:
            return set()
    return set()

def save_uploaded(s):
    DBFILE.write_text(json.dumps(list(s)))

def run_once():
    if not GARMIN_USER or not GARMIN_PASS:
        logger.error("환경변수 GARMIN_USER 및 GARMIN_PASS를 .env에 설정하세요.")
        return

    uploaded = load_uploaded()
    g = GarminClient(GARMIN_USER, GARMIN_PASS)
    try:
        g.login()
    except Exception as e:
        logger.exception(f"Garmin 로그인 실패: {e}")
        return

    acts = g.list_recent_activities(limit=20)
    uploader = DriveUploader()
    new_uploaded = set(uploaded)

    for a in acts:
        aid = a.get('activityId')
        start_time = a.get('startTimeLocal') or a.get('startTime') or a.get('startTimeGMT')
        try:
            if start_time:
                year = datetime.fromisoformat(start_time.split('.')[0]).year
            else:
                year = datetime.now().year
        except Exception:
            year = datetime.now().year

        if str(aid) in uploaded:
            logger.info(f"{aid} 이미 업로드됨, 건너뜀")
            continue

        filename = f"{aid}.fit"
        local_path = TMPDIR / filename
        try:
            logger.info(f"다운로드 시도 activityId={aid}")
            g.download_activity_fit(aid, str(local_path))

            path_list = ['Garmin', 'Run', str(year)]
            logger.info(f"업로드 경로: {'/'.join(path_list)} (parent_id={DRIVE_PARENT_FOLDER_ID})")

            uploaded_file_id = uploader.upload_file_with_path(str(local_path), path_list, root_parent_id=DRIVE_PARENT_FOLDER_ID)
            logger.info(f"업로드 완료: file_id={uploaded_file_id}")

            df = fit_to_dataframe(str(local_path))
            summ = zone2_summary(df)
            logger.info(f"Zone2 summary for {aid}: {summ}")

            new_uploaded.add(str(aid))
        except Exception as e:
            logger.exception(f"activity {aid} 처리 중 오류: {e}")

    save_uploaded(new_uploaded)
    logger.info("작업 완료.")

if __name__ == "__main__":
    try:
        os.chdir(WORKDIR)
    except Exception:
        pass
    run_once()
