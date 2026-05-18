import json
from pathlib import Path

from class_up.config import AnalysisConfig, AppConfig, MediaConfig, OutputConfig, ProjectConfig, TranscriptionConfig
from class_up.manifest import Manifest, error_info


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        project=ProjectConfig(output_root=str(tmp_path)),
        media=MediaConfig(),
        transcription=TranscriptionConfig(api_key_env="SECRET_ENV"),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )


def test_manifest_initializes_without_secret_value(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_ENV", "real-secret")
    video = tmp_path / "course.mp4"
    video.write_bytes(b"video")
    manifest = Manifest.create(video, tmp_path / "outputs", _config(tmp_path))
    manifest.save()
    data = json.loads(manifest.path.read_text(encoding="utf-8"))
    assert data["input"]["video_path"] == str(video.resolve())
    assert data["stages"]["m1"]["status"] == "pending"
    assert "real-secret" not in manifest.path.read_text(encoding="utf-8")


def test_manifest_stage_and_error_update(tmp_path):
    video = tmp_path / "course.mp4"
    video.write_bytes(b"video")
    manifest = Manifest.create(video, tmp_path / "outputs", _config(tmp_path))
    failure = error_info("CONFIG_INVALID", "bad config")
    manifest.set_stage("m1", "failed", failure)
    assert manifest.data["status"] == "failed"
    assert manifest.data["stages"]["m1"]["error"]["code"] == "CONFIG_INVALID"
