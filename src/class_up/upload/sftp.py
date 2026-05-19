from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from class_up.config import UploadConfig
from class_up.upload.base import UploadedAudio, UploadService


class SftpUploadService(UploadService):
    def __init__(self, config: UploadConfig):
        self.config = config

    def upload_audio(self, local_path: Path, remote_name: str) -> UploadedAudio:
        host = os.environ.get(self.config.host_env, "").strip()
        username = os.environ.get(self.config.username_env, "").strip()
        key_path = os.environ.get(self.config.private_key_path_env, "").strip()
        if not host:
            raise ValueError(f"missing upload host env: {self.config.host_env}")
        if not username:
            raise ValueError(f"missing upload username env: {self.config.username_env}")
        if not key_path:
            raise ValueError(f"missing upload private key path env: {self.config.private_key_path_env}")

        try:
            import paramiko  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("paramiko is required for SFTP upload. Install with: pip install -e .") from exc

        remote_dir = self.config.remote_dir.rstrip("/")
        remote_path = f"{remote_dir}/{remote_name}"
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(hostname=host, port=self.config.port, username=username, key_filename=key_path, timeout=30)
            sftp = client.open_sftp()
            try:
                sftp.put(str(local_path), remote_path)
            finally:
                sftp.close()
        finally:
            client.close()

        public_base = self.config.public_url_base.rstrip("/")
        return UploadedAudio(public_url=f"{public_base}/{quote(remote_name)}", remote_name=remote_name)
