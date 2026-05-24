from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from class_up.config import AnalysisConfig, AppConfig, MediaConfig, OutputConfig, ProjectConfig, TranscriptionConfig, UploadConfig
from class_up.manifest import Manifest
from class_up.transcription.service import transcribe_segments
from class_up.upload import UploadError


class FlakyTranscriptionService:
    provider = "test"

    def __init__(self, failures_before_success: int):
        self.failures_before_success = failures_before_success
        self.calls = 0

    def transcribe(self, segment: dict[str, Any], audio_path: Path) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise UploadError("remote size mismatch: local=10 remote=1")
        return {
            "schema_version": "1.0",
            "segment_id": segment["segment_id"],
            "source_audio": segment["audio_path"],
            "time_base": "segment_relative",
            "language": "zh",
            "provider": self.provider,
            "model": "",
            "items": [{"item_id": f"{segment['segment_id']}-item-0001", "start": 0.0, "end": 1.0, "text": "ok", "confidence": None}],
            "raw_output_path": None,
            "error": None,
        }


def _config(max_retries: int) -> AppConfig:
    return AppConfig(
        project=ProjectConfig(),
        media=MediaConfig(),
        transcription=TranscriptionConfig(provider="mock", max_retries=max_retries),
        upload=UploadConfig(),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )


def _manifest(tmp_path, config: AppConfig) -> Manifest:
    video = tmp_path / "course.mp4"
    video.write_bytes(b"video")
    manifest = Manifest.create(video, tmp_path / "outputs", config)
    segment_audio = manifest.output_dir / "intermediate" / "segments" / "segment-0001.wav"
    segment_audio.parent.mkdir(parents=True)
    segment_audio.write_bytes(b"audio")
    manifest.set_segments(
        [
            {
                "segment_id": "segment-0001",
                "parent_segment_id": None,
                "index": 1,
                "status": "ready",
                "start": 0.0,
                "end": 1.0,
                "overlap_previous_seconds": 0,
                "overlap_next_seconds": 0,
                "audio_path": "intermediate/segments/segment-0001.wav",
                "size_bytes": 5,
                "upload_limit_mb": 25,
                "transcription_path": None,
                "retry_count": 0,
                "error": None,
            }
        ]
    )
    manifest.save()
    return manifest


def test_transcribe_segments_retries_retryable_failure_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("class_up.transcription.service.time.sleep", lambda seconds: None)
    config = _config(max_retries=1)
    manifest = _manifest(tmp_path, config)
    service = FlakyTranscriptionService(failures_before_success=1)

    transcribe_segments(manifest, config, service=service)

    segment = manifest.data["segments"][0]
    assert service.calls == 2
    assert segment["status"] == "success"
    assert segment["retry_count"] == 1
    assert segment["error"] is None


def test_transcribe_segments_fails_after_retry_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("class_up.transcription.service.time.sleep", lambda seconds: None)
    config = _config(max_retries=1)
    manifest = _manifest(tmp_path, config)
    service = FlakyTranscriptionService(failures_before_success=3)

    with pytest.raises(UploadError):
        transcribe_segments(manifest, config, service=service)

    segment = manifest.data["segments"][0]
    assert service.calls == 2
    assert segment["status"] == "failed"
    assert segment["retry_count"] == 1
    assert "attempt=2/2" in segment["error"]["detail"]
    assert "UploadError" in segment["error"]["detail"]
