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
INITFILE = WORKDIR / ".sync_initialized"

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

def is_first_run():
    """초기 동기화 여부 확인"""
    return not INITFILE.exists()

def mark_initialized():
    """초기 동기화 완료 표시"""
    INITFILE.touch()
    logger.info("초기 동기화 완료. 다음부터 최근 데이터만 동기화합니다.")

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

    # 활동 목록 가져오기
    first_run = is_first_run()
    if first_run:
        logger.info("🔄 초기 동기화 모드: 모든 과거 데이터를 받아옵니다...")
        acts = g.list_all_activities(batch_size=100)
    else:
        logger.info("📊 정기 동기화 모드: 최근 20개 활동을 받아옵니다...")
        acts = g.list_recent_activities(limit=20)
    
    uploader = DriveUploader()
    new_uploaded = set(uploaded)
    total_acts = len(acts)
    processed = 0
    uploaded_count = 0

    for a in acts:
        processed += 1
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
            logger.info(f"[{processed}/{total_acts}] 활동 {aid}: 이미 업로드됨, 건너뜀")
            continue

        filename = f"activity_{aid}_{datetime.fromisoformat(start_time.split('.')[0]).strftime('%Y-%m-%d')}.fit" if start_time else f"{aid}.fit"
        local_path = TMPDIR / filename
        try:
            logger.info(f"[{processed}/{total_acts}] 활동 {aid}: 다운로드 중...")
            g.download_activity_fit(aid, str(local_path))
            
            logger.info(f"[{processed}/{total_acts}] 활동 {aid}: 파일 크기 {local_path.stat().st_size / 1024:.1f} KB")

            path_list = ['Garmin', 'Run', str(year)]
            logger.info(f"[{processed}/{total_acts}] 활동 {aid}: Google Drive에 업로드 중 ({'/'.join(path_list)})...")

            uploaded_file_id = uploader.upload_file_with_path(str(local_path), path_list, root_parent_id=DRIVE_PARENT_FOLDER_ID)
            logger.info(f"[{processed}/{total_acts}] 활동 {aid}: ✅ 업로드 완료 (file_id={uploaded_file_id})")
            
            uploaded_count += 1

            try:
                df = fit_to_dataframe(str(local_path))
                summ = zone2_summary(df)
                logger.info(f"[{processed}/{total_acts}] 활동 {aid} Zone2 분석: {summ}")
            except Exception as fit_error:
                logger.warning(f"[{processed}/{total_acts}] 활동 {aid} FIT 분석 실패 (건너뜀): {fit_error}")

            new_uploaded.add(str(aid))
        except Exception as e:
            logger.exception(f"[{processed}/{total_acts}] 활동 {aid} 처리 중 오류: {e}")

    save_uploaded(new_uploaded)
    
    # 초기 동기화 완료 표시
    if first_run and uploaded_count > 0:
        mark_initialized()
    
    logger.info(f"✅ 작업 완료. (새로 업로드: {uploaded_count}개, 이미 업로드된 활동: {len(new_uploaded) - uploaded_count}개)")

if __name__ == "__main__":
    try:
        os.chdir(WORKDIR)
    except Exception:
        pass
    run_once()
