# scripts/drive_uploader.py
import logging
import os
from typing import Optional

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

logger = logging.getLogger(__name__)

class DriveUploader:
    def __init__(self, settings_file='settings.yaml'):
        self.gauth = GoogleAuth(settings_file=settings_file)
        logger.info("GoogleAuth: LocalWebserverAuth 시도 (첫 실행시 브라우저 인증 필요)")
        try:
            self.gauth.LocalWebserverAuth()
        except Exception as e:
            logger.error(f"Google Drive 인증 실패: {e}")
            raise RuntimeError(
                "Google Drive 인증에 실패했습니다. "
                "settings.yaml과 client_secrets.json을 확인하세요."
            ) from e
        self.drive = GoogleDrive(self.gauth)

    def _get_folder_id(self, folder_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        safe_name = folder_name.replace("\\", "\\\\").replace("'", "\\'")
        q = f"mimeType='application/vnd.google-apps.folder' and trashed=false and title='{safe_name}'"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        file_list = self.drive.ListFile({'q': q}).GetList()
        if file_list:
            return file_list[0]['id']
        return None

    def get_or_create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        folder_id = self._get_folder_id(folder_name, parent_id)
        if folder_id:
            logger.info(f"폴더 존재: {folder_name} (id={folder_id})")
            return folder_id
        metadata = {'title': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id:
            metadata['parents'] = [{'id': parent_id}]
        folder = self.drive.CreateFile(metadata)
        folder.Upload()
        logger.info(f"폴더 생성: {folder_name} (id={folder['id']})")
        return folder['id']

    def _find_file_in_folder(self, filename: str, folder_id: str) -> Optional[str]:
        safe_name = filename.replace("\\", "\\\\").replace("'", "\\'")
        q = (
            f"title='{safe_name}' and trashed=false "
            f"and '{folder_id}' in parents"
        )
        file_list = self.drive.ListFile({'q': q}).GetList()
        if file_list:
            return file_list[0]['id']
        return None

    def upload_file_to_folder(self, local_path: str, folder_id: str) -> str:
        fname = os.path.basename(local_path)
        existing_id = self._find_file_in_folder(fname, folder_id)
        if existing_id:
            logger.info(f"이미 존재하는 파일 업데이트: {fname} (id={existing_id})")
            gfile = self.drive.CreateFile({'id': existing_id})
        else:
            metadata = {'title': fname, 'parents': [{'id': folder_id}]}
            gfile = self.drive.CreateFile(metadata)
        gfile.SetContentFile(local_path)
        gfile.Upload()
        logger.info(f"Uploaded {local_path} -> {fname} (id={gfile['id']})")
        return gfile['id']

    def upload_file_with_path(self, local_path: str, path_list: list, root_parent_id: Optional[str] = None) -> str:
        parent = root_parent_id
        for folder in path_list:
            parent = self.get_or_create_folder(folder, parent)
        return self.upload_file_to_folder(local_path, parent)
