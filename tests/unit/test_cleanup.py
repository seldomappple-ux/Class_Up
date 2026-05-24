from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from class_up.cleanup import CleanupCandidate, build_cleanup_plan, cleanup_remote_audio_record, execute_cleanup_plan
from class_up.config import AnalysisConfig, AppConfig, CleanupConfig, MediaConfig, OutputConfig, ProjectConfig, TranscriptionConfig, UploadConfig
from class_up.manifest import Manifest


def _config() -> AppConfig:
    return AppConfig(
        project=ProjectConfig(),
        media=MediaConfig(),
        transcription=TranscriptionConfig(),
        upload=UploadConfig(),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )


def _make_manifest(tmp_path: Path, status: str = "success") -> Manifest:
    uploads = tmp_path / "outputs" / "uploads" / "abc"
    uploads.mkdir(parents=True)
    video = uploads / "video.mp4"
    video.write_bytes(b"video")
    manifest = Manifest.create(video, tmp_path / "outputs", _config(), course_title="course")
    intermediate = manifest.output_dir / "intermediate" / "segments"
    intermediate.mkdir(parents=True)
    (intermediate / "segment-0001.wav").write_bytes(b"audio")
    manifest.data["status"] = status
    manifest.data["updated_at"] = (datetime.now(timezone.utc).astimezone() - timedelta(days=8)).isoformat(timespec="seconds")
    manifest.path.write_text(json.dumps(manifest.data, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def test_cleanup_plan_marks_old_upload_and_intermediate(tmp_path):
    manifest = _make_manifest(tmp_path, status="success")
    plan = build_cleanup_plan(
        output_root=tmp_path / "outputs",
        cleanup=CleanupConfig(successful_upload_ttl_hours=24, intermediate_ttl_hours=168),
        target="local",
    )

    paths = {item.path for item in plan}
    assert str(Path(manifest.data["input"]["video_path"])) in paths
    assert str(manifest.output_dir / "intermediate") in paths


def test_cleanup_dry_run_does_not_delete_files(tmp_path):
    manifest = _make_manifest(tmp_path, status="success")
    candidate = CleanupCandidate(
        target_type="local_uploaded_video",
        path=manifest.data["input"]["video_path"],
        reason="test",
        bytes=5,
    )

    result = execute_cleanup_plan([candidate], dry_run=True, audit_path=tmp_path / "audit.jsonl")

    assert result["count"] == 1
    assert Path(manifest.data["input"]["video_path"]).exists()


def test_cleanup_execute_deletes_intermediate_but_keeps_manifest_and_outputs(tmp_path):
    manifest = _make_manifest(tmp_path, status="success")
    subtitle = manifest.output_dir / "lesson_Subtitles.srt"
    subtitle.write_text("subtitle", encoding="utf-8")
    candidate = CleanupCandidate(
        target_type="local_intermediate_cache",
        path=str(manifest.output_dir / "intermediate"),
        reason="test",
        bytes=5,
    )

    execute_cleanup_plan([candidate], dry_run=False, audit_path=tmp_path / "audit.jsonl")

    assert not (manifest.output_dir / "intermediate").exists()
    assert manifest.path.exists()
    assert subtitle.exists()


def test_cleanup_remote_audio_record_logs_failure_without_raising(tmp_path, monkeypatch):
    class FailingUpload:
        def __init__(self, config):
            pass

        def delete_audio(self, remote_name: str) -> None:
            raise RuntimeError("cannot delete")

    monkeypatch.setattr("class_up.cleanup.SftpUploadService", FailingUpload)

    event = cleanup_remote_audio_record(
        UploadConfig(provider="sftp"),
        {"remote_name": "a_segment-0001.wav", "remote_path": "/remote/a_segment-0001.wav", "size_bytes": 10},
        audit_path=tmp_path / "audit.jsonl",
    )

    assert event["success"] is False
    assert "cannot delete" in event["error"]


def test_cleanup_plan_adds_disk_pressure_candidates(tmp_path):
    manifest = _make_manifest(tmp_path, status="success")

    plan = build_cleanup_plan(
        output_root=tmp_path / "outputs",
        cleanup=CleanupConfig(
            successful_upload_ttl_hours=9999,
            intermediate_ttl_hours=9999,
            disk_min_free_gb=10,
        ),
        target="local",
        disk_usage_func=lambda path: SimpleNamespace(free=1),
    )

    reasons = {item.reason for item in plan}
    assert "disk_pressure_uploaded_video" in reasons
    assert "disk_pressure_intermediate/segments" in reasons
    assert manifest.path.exists()
