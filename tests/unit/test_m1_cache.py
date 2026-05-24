from __future__ import annotations

import json

import class_up.api.jobs as jobs
from class_up.config import AnalysisConfig, AppConfig, MediaConfig, OutputConfig, ProjectConfig, TranscriptionConfig, UploadConfig
from class_up.manifest import Manifest


def _config() -> AppConfig:
    return AppConfig(
        project=ProjectConfig(),
        media=MediaConfig(segment_seconds=600, overlap_seconds=30),
        transcription=TranscriptionConfig(provider="doubao", endpoint="https://openspeech.bytedance.com", model="bigmodel", resource_id="volc.seedasr.auc"),
        upload=UploadConfig(provider="sftp"),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )


def _write_transcription(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "segment_id": "segment-0001",
                "source_audio": "intermediate/segments/segment-0001.wav",
                "time_base": "segment_relative",
                "language": "zh",
                "provider": "doubao",
                "model": "bigmodel",
                "items": [{"item_id": "segment-0001-item-0001", "start": 0.0, "end": 1.0, "text": "cached", "confidence": None}],
                "raw_output_path": None,
                "error": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_reuse_completed_m1_cache_copies_intermediate_and_segments(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "OUTPUT_ROOT", tmp_path / "outputs")
    config = _config()
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"same-video")

    cached = Manifest.create(source_video, jobs.OUTPUT_ROOT, config, course_title="source")
    segment_audio = cached.output_dir / "intermediate" / "segments" / "segment-0001.wav"
    segment_audio.parent.mkdir(parents=True, exist_ok=True)
    segment_audio.write_bytes(b"audio")
    transcription = cached.output_dir / "intermediate" / "transcription" / "segment-0001.json"
    _write_transcription(transcription)
    cached.set_duration(1.0)
    cached.set_normalized_audio(cached.output_dir / "intermediate" / "audio" / "full_audio.wav", "wav", 16000, 1)
    (cached.output_dir / "intermediate" / "audio").mkdir(parents=True, exist_ok=True)
    (cached.output_dir / "intermediate" / "audio" / "full_audio.wav").write_bytes(b"audio")
    cached.set_segments(
        [
            {
                "segment_id": "segment-0001",
                "parent_segment_id": None,
                "index": 1,
                "status": "success",
                "start": 0.0,
                "end": 1.0,
                "overlap_previous_seconds": 0,
                "overlap_next_seconds": 0,
                "audio_path": "intermediate/segments/segment-0001.wav",
                "size_bytes": 5,
                "upload_limit_mb": 25,
                "transcription_path": "intermediate/transcription/segment-0001.json",
                "retry_count": 0,
                "error": None,
            }
        ]
    )
    cached.set_stage("m1", "success")
    cached.save()

    current_video = tmp_path / "copy.mp4"
    current_video.write_bytes(b"same-video")
    current = Manifest.create(current_video, jobs.OUTPUT_ROOT, config, course_title="copy")
    current.save()

    assert jobs._reuse_completed_m1_cache(current) is True
    assert current.data["segments"][0]["status"] == "success"
    assert (current.output_dir / "intermediate" / "transcription" / "segment-0001.json").exists()
    assert current.data["media"]["source_video"]["path"] == str(current_video.resolve())
    assert current.data["reviews"][0]["type"] == "m1_cache_reuse"
