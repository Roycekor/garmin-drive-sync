# scripts/drive_uploader.py
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DriveUploader:
    def __init__(self, settings_file='settings.yaml'):
        self.gauth = GoogleAuth(settings_file=settings_file)
        logger.info("GoogleAuth: LocalWebserverAuth 시도 (첫 실행시 브라우저 인증 필요)")
        self.gauth.LocalWebserverAuth()
        self.drive = GoogleDrive(self.gauth)

    def _get_folder_id(self, folder_name: str, parent_id: Optional[str]=None) -> Optional[str]:
        q = f"mimeType='application/vnd.google-apps.folder' and trashed=false and title='{folder_name}'"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        file_list = self.drive.ListFile({'q': q}).GetList()
        if file_list:
            return file_list[0]['id']
        return None

    def get_or_create_folder(self, folder_name: str, parent_id: Optional[str]=None) -> str:
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

    def upload_file_to_folder(self, local_path: str, folder_id: str) -> str:
        fname = os.path.basename(local_path)
        metadata = {'title': fname, 'parents': [{'id': folder_id}]}
        gfile = self.drive.CreateFile(metadata)
        gfile.SetContentFile(local_path)
        gfile.Upload()
        logger.info(f"Uploaded {local_path} -> {fname} (id={gfile.get('id')})")
        return gfile['id']

    def upload_file_with_path(self, local_path: str, path_list: list, root_parent_id: Optional[str]=None) -> str:
        parent = root_parent_id
        for folder in path_list:
            parent = self.get_or_create_folder(folder, parent)
        return self.upload_file_to_folder(local_path, parent)
