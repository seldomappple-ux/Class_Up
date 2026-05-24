from __future__ import annotations

import types

import pytest

from class_up.config import UploadConfig
from class_up.upload.sftp import SftpUploadService, UploadError


class FakeSftp:
    def __init__(self, remote_size: int):
        self.remote_size = remote_size
        self.put_calls: list[tuple[str, str]] = []
        self.removed: list[str] = []

    def put(self, local_path: str, remote_path: str) -> None:
        self.put_calls.append((local_path, remote_path))

    def stat(self, remote_path: str):
        return types.SimpleNamespace(st_size=self.remote_size)

    def remove(self, remote_path: str) -> None:
        self.removed.append(remote_path)

    def close(self) -> None:
        pass


class FakeSshClient:
    def __init__(self, sftp: FakeSftp):
        self.sftp = sftp

    def load_system_host_keys(self) -> None:
        pass

    def set_missing_host_key_policy(self, policy) -> None:
        pass

    def connect(self, **kwargs) -> None:
        pass

    def open_sftp(self) -> FakeSftp:
        return self.sftp

    def close(self) -> None:
        pass


def _install_fake_paramiko(monkeypatch, sftp: FakeSftp) -> None:
    fake_paramiko = types.SimpleNamespace(
        SSHClient=lambda: FakeSshClient(sftp),
        AutoAddPolicy=lambda: object(),
    )
    monkeypatch.setitem(__import__("sys").modules, "paramiko", fake_paramiko)


def _set_upload_env(monkeypatch, key_path: str) -> None:
    monkeypatch.setenv("CLASS_UP_UPLOAD_HOST", "example.com")
    monkeypatch.setenv("CLASS_UP_UPLOAD_USER", "ubuntu")
    monkeypatch.setenv("CLASS_UP_UPLOAD_KEY_PATH", key_path)


def test_sftp_upload_succeeds_when_remote_size_matches(tmp_path, monkeypatch):
    audio = tmp_path / "segment.wav"
    audio.write_bytes(b"audio-bytes")
    sftp = FakeSftp(remote_size=audio.stat().st_size)
    _install_fake_paramiko(monkeypatch, sftp)
    _set_upload_env(monkeypatch, str(tmp_path / "key"))

    uploaded = SftpUploadService(UploadConfig(provider="sftp")).upload_audio(audio, "segment.wav")

    assert uploaded.public_url == "https://boneorbit.com/class-up/audio/segment.wav"
    assert uploaded.remote_path == "/var/www/class-up/audio/segment.wav"
    assert sftp.put_calls == [(str(audio), "/var/www/class-up/audio/segment.wav")]
    assert sftp.removed == []


def test_sftp_upload_size_mismatch_removes_remote_and_raises(tmp_path, monkeypatch):
    audio = tmp_path / "segment.wav"
    audio.write_bytes(b"audio-bytes")
    sftp = FakeSftp(remote_size=1)
    _install_fake_paramiko(monkeypatch, sftp)
    _set_upload_env(monkeypatch, str(tmp_path / "key"))

    with pytest.raises(UploadError, match="size mismatch") as exc:
        SftpUploadService(UploadConfig(provider="sftp")).upload_audio(audio, "segment.wav")

    assert exc.value.retryable is True
    assert sftp.removed == ["/var/www/class-up/audio/segment.wav"]


def test_sftp_delete_audio_removes_remote_file(tmp_path, monkeypatch):
    sftp = FakeSftp(remote_size=0)
    _install_fake_paramiko(monkeypatch, sftp)
    _set_upload_env(monkeypatch, str(tmp_path / "key"))

    SftpUploadService(UploadConfig(provider="sftp")).delete_audio("segment.wav")

    assert sftp.removed == ["/var/www/class-up/audio/segment.wav"]
