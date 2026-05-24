from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from class_up.config import UploadConfig
from class_up.upload.base import UploadedAudio, UploadService


class UploadError(RuntimeError):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


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
        local_size = local_path.stat().st_size
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            try:
                client.connect(hostname=host, port=self.config.port, username=username, key_filename=key_path, timeout=30)
            except Exception as exc:
                raise UploadError(f"SFTP connection failed: {exc}") from exc
            try:
                sftp = client.open_sftp()
            except Exception as exc:
                raise UploadError(f"SFTP session failed: {exc}") from exc
            try:
                try:
                    sftp.put(str(local_path), remote_path)
                    remote_size = sftp.stat(remote_path).st_size
                except Exception as exc:
                    raise UploadError(f"SFTP upload failed: remote_path={remote_path}, detail={exc}") from exc
                if remote_size != local_size:
                    try:
                        sftp.remove(remote_path)
                    except Exception:
                        pass
                    raise UploadError(
                        "SFTP upload size mismatch: "
                        f"remote_path={remote_path}, local_size={local_size}, remote_size={remote_size}"
                    )
            finally:
                sftp.close()
        finally:
            client.close()

        public_base = self.config.public_url_base.rstrip("/")
        return UploadedAudio(public_url=f"{public_base}/{quote(remote_name)}", remote_name=remote_name)
