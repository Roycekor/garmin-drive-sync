# scripts/garmin_client.py
from garminconnect import Garmin
import logging
import stat
import zipfile
import io
from pathlib import Path

logger = logging.getLogger(__name__)

class GarminClient:
    def __init__(self, username: str, password: str, tokenstore: str | Path = None):
        self.username = username
        self.password = password
        self.tokenstore = Path(tokenstore) if tokenstore else None
        self.client = None

    def login(self):
        # garminconnect 0.3.x: login(path)이 토큰 로드 → 실패 시 credential 로그인 → 성공 시 자동 저장
        tokenstore_str = str(self.tokenstore) if self.tokenstore else None
        self.client = Garmin(self.username, self.password)
        logger.info("Garmin 로그인 시도")
        self.client.login(tokenstore_str)
        logger.info("Garmin 로그인 성공")

        # 자동 저장된 토큰 파일 권한 강화 (소유자 전용) — drive_uploader/garmin_browser_auth와 일관성
        if self.tokenstore:
            token_file = self.tokenstore / "garmin_tokens.json"
            if token_file.exists():
                token_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def list_recent_activities(self, limit=20):
        return self.client.get_activities(0, limit)

    def list_all_activities(self, batch_size=100):
        """모든 활동을 페이지네이션으로 가져옵니다 (과거 데이터 포함)"""
        all_activities = []
        offset = 0
        while True:
            activities = self.client.get_activities(offset, batch_size)
            if not activities:
                break
            all_activities.extend(activities)
            logger.info(f"활동 {len(all_activities)}개 로드 완료")
            offset += batch_size
        return all_activities

    def download_activity_fit(self, activity_id, out_path):
        fit_data = self.client.download_activity(
            activity_id,
            dl_fmt=self.client.ActivityDownloadFormat.ORIGINAL
        )

        # ORIGINAL 형식은 ZIP 파일이므로 압축 해제
        try:
            with zipfile.ZipFile(io.BytesIO(fit_data)) as zip_ref:
                # ZIP 내 .fit 파일 찾기
                fit_files = [f for f in zip_ref.namelist() if f.endswith('.fit')]
                if fit_files:
                    # 첫 번째 .fit 파일 추출
                    fit_filename = fit_files[0]
                    fit_content = zip_ref.read(fit_filename)
                    with open(out_path, "wb") as f:
                        f.write(fit_content)
                    logger.info(f"FIT 다운로드 완료: {out_path} (ZIP에서 {fit_filename} 추출)")
                    return out_path
                else:
                    # .fit 파일이 없으면 ZIP의 첫 파일 추출 시도
                    if zip_ref.namelist():
                        first_file = zip_ref.namelist()[0]
                        content = zip_ref.read(first_file)
                        with open(out_path, "wb") as f:
                            f.write(content)
                        logger.info(f"FIT 다운로드 완료: {out_path} (ZIP에서 {first_file} 추출)")
                        return out_path
                    else:
                        raise ValueError("ZIP 파일이 비어있음")
        except zipfile.BadZipFile:
            # ZIP이 아닌 경우 그대로 저장 (호환성)
            logger.warning("ZIP 파일이 아님, 그대로 저장합니다")
            with open(out_path, "wb") as f:
                f.write(fit_data)
            logger.info(f"FIT 다운로드 완료: {out_path}")
            return out_path
