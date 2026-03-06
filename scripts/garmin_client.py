# scripts/garmin_client.py
from garminconnect import Garmin
import logging

logger = logging.getLogger(__name__)

class GarminClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.client = None

    def login(self):
        self.client = Garmin(self.username, self.password)
        logger.info("Garmin 로그인 시도")
        self.client.login()
        logger.info("Garmin 로그인 성공")

    def list_recent_activities(self, limit=20):
        return self.client.get_activities(0, limit)

    def download_activity_fit(self, activity_id, out_path):
        fit_data = self.client.download_activity(
            activity_id,
            dl_fmt=self.client.ActivityDownloadFormat.FIT
        )
        with open(out_path, "wb") as f:
            f.write(fit_data)
        logger.info(f"FIT 다운로드 완료: {out_path}")
        return out_path
