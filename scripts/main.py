# scripts/main.py
import os
import logging
import json
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# load .env from project root
load_dotenv()

from garmin_client import GarminClient
from drive_uploader import DriveUploader
from fit_analyzer import (fit_to_dataframe, get_fit_sport, zone2_summary, save_zone2_analysis,
                          run_summary, hr_drift, pace_stability, save_run_analysis)

# 활동 타입 매핑
ACTIVITY_TYPE_MAPPING = {
    'running': 'Run',
    'walking': 'Walk',
    'cycling': 'Bike',
    'indoor_cycling': 'Bike',
    'mountain_biking': 'Bike',
    'lap_swimming': 'Swim',
    'open_water_swimming': 'Swim',
    'pool_swimming': 'Swim',
    'hiking': 'Hike',
    'trail_running': 'Trail',
    'strength_training': 'Strength',
    'yoga': 'Yoga',
    'pilates': 'Pilates',
    'elliptical': 'Elliptical',
    'rowing': 'Rowing',
}

def parse_args():
    parser = argparse.ArgumentParser(description='Garmin to Google Drive Sync')
    parser.add_argument('--analyze-only', action='store_true', help='로컬 FIT 파일들만 분석 (업로드하지 않음)')
    return parser.parse_args()

# 환경/경로 설정
GARMIN_USER = os.environ.get('GARMIN_USER')
GARMIN_PASS = os.environ.get('GARMIN_PASS')
DRIVE_PARENT_FOLDER_ID = os.environ.get('DRIVE_PARENT_FOLDER_ID')
WORKDIR = Path(os.environ.get('WORKDIR', Path.home() / "garmin-drive-sync"))
TMPDIR = WORKDIR / "tmp"
LOGFILE = WORKDIR / "logs/sync.log"
DBFILE = WORKDIR / "uploaded.json"
DB_ANALYSIS = WORKDIR / "analysis.db"
INITFILE = WORKDIR / ".sync_initialized"
ANALYZE_MARKER = WORKDIR / ".analyze_marker"
DASHBOARD_CONFIG = WORKDIR / "config" / "dashboard.json"

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

def analyze_local_files():
    """로컬 FIT 파일들만 분석 (마커 파일 이후 새 파일만)"""
    logger.info("🔍 로컬 FIT 파일 분석 모드 시작...")
    all_fit_files = list(TMPDIR.glob("*.fit"))
    if not all_fit_files:
        logger.info("분석할 FIT 파일이 없습니다.")
        return

    # 마커 파일보다 새로운 FIT 파일만 필터링
    if ANALYZE_MARKER.exists():
        marker_mtime = ANALYZE_MARKER.stat().st_mtime
        fit_files = [f for f in all_fit_files if f.stat().st_mtime > marker_mtime]
        logger.info(f"총 {len(all_fit_files)}개 FIT 파일 중 {len(fit_files)}개 신규 파일 발견")
    else:
        fit_files = all_fit_files
        logger.info(f"총 {len(fit_files)}개 FIT 파일 발견 (첫 분석)")

    if not fit_files:
        logger.info("새로 분석할 FIT 파일이 없습니다.")
        sync_db_to_dashboard()
        return

    total_files = len(fit_files)
    for i, fit_path in enumerate(fit_files, 1):
        try:
            # 파일명에서 activityId 추출 (activity_{aid}_... 또는 {aid}.fit)
            filename = fit_path.name
            if filename.startswith("activity_"):
                aid = filename.split("_")[1]
            else:
                aid = filename.split(".")[0]
            
            # FIT 파일에서 활동 타입 확인 — running만 분석
            sport = get_fit_sport(str(fit_path))
            if sport != 'running':
                logger.info(f"[{i}/{total_files}] 파일 {filename}: {sport} (러닝 아님, 건너뜀)")
                continue

            logger.info(f"[{i}/{total_files}] 파일 {filename} 분석 중...")

            df = fit_to_dataframe(str(fit_path))
            summ = zone2_summary(df)
            logger.info(f"[{i}/{total_files}] 파일 {filename} Zone2 분석: {summ}")

            # 통합 분석
            summary = run_summary(df)
            drift = hr_drift(df)
            stability = pace_stability(df)
            data = {**summary, **summ, 'hr_drift_percent': drift, 'pace_stability_cv': stability}
            save_run_analysis(str(DB_ANALYSIS), filename, data)

            # 기존 zone2 테이블에도 저장 (하위호환)
            save_zone2_analysis(str(DB_ANALYSIS), filename, summ)
            
        except Exception as e:
            logger.warning(f"[{i}/{total_files}] 파일 {filename} 분석 실패: {e}")
    
    ANALYZE_MARKER.touch()
    logger.info("✅ 로컬 FIT 파일 분석 완료")
    sync_db_to_dashboard()

def sync_db_to_dashboard():
    """analysis.db를 대시보드 저장소로 복사"""
    if not DASHBOARD_CONFIG.exists():
        logger.debug("dashboard.json 설정 없음, DB 복사 건너뜀")
        return
    try:
        config = json.loads(DASHBOARD_CONFIG.read_text())
        repo_path = Path(config.get('repo_path', ''))
        if not repo_path.is_dir():
            logger.warning(f"대시보드 저장소 경로가 존재하지 않음: {repo_path}")
            return
        shutil.copy2(str(DB_ANALYSIS), str(repo_path / "analysis.db"))
        logger.info(f"analysis.db → {repo_path} 복사 완료")

        # git repo 확인
        git_check = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            cwd=str(repo_path), capture_output=True
        )
        if git_check.returncode != 0:
            logger.info("대시보드 저장소에 git 설정 없음, push 건너뜀")
            return

        # git add, commit, push
        result = subprocess.run(
            ['git', 'diff', '--quiet', 'analysis.db'],
            cwd=str(repo_path), capture_output=True
        )
        if result.returncode == 0:
            logger.info("analysis.db 변경 없음, push 건너뜀")
            return
        subprocess.run(['git', 'add', 'analysis.db'], cwd=str(repo_path), check=True)
        subprocess.run(
            ['git', 'commit', '-m', '[data] update analysis.db'],
            cwd=str(repo_path), check=True
        )
        subprocess.run(['git', 'pull', '--rebase'], cwd=str(repo_path), check=True)
        subprocess.run(['git', 'push'], cwd=str(repo_path), check=True)
        logger.info("대시보드 저장소 git push 완료")
    except Exception as e:
        logger.warning(f"대시보드 DB 동기화 실패: {e}")


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
    g = GarminClient(GARMIN_USER, GARMIN_PASS, tokenstore=WORKDIR / ".garmin_tokens")

    try:
        g.login()
    except Exception as e:
        if "429" in str(e):
            logger.error("Garmin 로그인 실패: 429 Too Many Requests — 잠시 후 다시 시도하세요.")
        else:
            logger.error(f"Garmin 로그인 실패: {e}")
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

    try:
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
                if not first_run:
                    logger.info(f"[{processed}/{total_acts}] 활동 {aid}: 이미 업로드됨 — 이후 활동 모두 건너뜀")
                    break
                logger.info(f"[{processed}/{total_acts}] 활동 {aid}: 이미 업로드됨, 건너뜀")
                continue

            filename = f"activity_{aid}_{datetime.fromisoformat(start_time.split('.')[0]).strftime('%Y-%m-%d')}.fit" if start_time else f"{aid}.fit"
            local_path = TMPDIR / filename
            try:
                logger.info(f"[{processed}/{total_acts}] 활동 {aid}: 다운로드 중...")
                g.download_activity_fit(aid, str(local_path))

                logger.info(f"[{processed}/{total_acts}] 활동 {aid}: 파일 크기 {local_path.stat().st_size / 1024:.1f} KB")

                # 활동 타입별로 폴더 결정
                activity_type_key = a.get('activityType', {}).get('typeKey', 'unknown')
                activity_folder = ACTIVITY_TYPE_MAPPING.get(activity_type_key, 'Other')
                path_list = ['Garmin', activity_folder, str(year)]
                logger.info(f"[{processed}/{total_acts}] 활동 {aid}: Google Drive에 업로드 중 ({activity_type_key} → {'/'.join(path_list)})...")

                uploaded_file_id = uploader.upload_file_with_path(str(local_path), path_list, root_parent_id=DRIVE_PARENT_FOLDER_ID)
                logger.info(f"[{processed}/{total_acts}] 활동 {aid}: ✅ 업로드 완료 (file_id={uploaded_file_id})")

                uploaded_count += 1
                new_uploaded.add(str(aid))
            except Exception as e:
                logger.exception(f"[{processed}/{total_acts}] 활동 {aid} 처리 중 오류: {e}")

        save_uploaded(new_uploaded)

        # 초기 동기화 완료 표시
        if first_run and uploaded_count > 0:
            mark_initialized()

        logger.info(f"✅ 작업 완료. (새로 업로드: {uploaded_count}개, 이미 업로드된 활동: {len(new_uploaded) - uploaded_count}개)")
    finally:
        # 다운로드된 FIT 파일 분석 (업로드 중 에러가 발생해도 분석은 실행)
        analyze_local_files()

if __name__ == "__main__":
    try:
        os.chdir(WORKDIR)
    except Exception:
        pass

    args = parse_args()
    if args.analyze_only:
        analyze_local_files()
    else:
        run_once()
