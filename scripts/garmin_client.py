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
        with open(out_path, "wb") as f:
            f.write(fit_data)
        logger.info(f"FIT 다운로드 완료: {out_path}")
        return out_path
