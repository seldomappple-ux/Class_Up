import json

from class_up.config import AnalysisConfig, AppConfig, MediaConfig, OutputConfig, ProjectConfig, TranscriptionConfig, UploadConfig
from class_up.manifest import Manifest
from class_up.transcription.merge import merge_transcriptions


def _config() -> AppConfig:
    return AppConfig(
        project=ProjectConfig(),
        media=MediaConfig(),
        transcription=TranscriptionConfig(),
        upload=UploadConfig(),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )


def _write_result(path, segment_id, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "segment_id": segment_id,
                "source_audio": f"intermediate/segments/{segment_id}.wav",
                "time_base": "segment_relative",
                "language": "zh",
                "provider": "mock",
                "model": "",
                "items": [{"item_id": f"{segment_id}-item-0001", "start": 0.0, "end": 1.0, "text": text, "confidence": None}],
                "raw_output_path": None,
                "error": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_merge_uses_index_not_segment_id(tmp_path):
    video = tmp_path / "course.mp4"
    video.write_bytes(b"video")
    manifest = Manifest.create(video, tmp_path / "outputs", _config())
    first = manifest.output_dir / "intermediate" / "transcription" / "segment-0003a.json"
    second = manifest.output_dir / "intermediate" / "transcription" / "segment-0002.json"
    _write_result(first, "segment-0003a", "first")
    _write_result(second, "segment-0002", "second")
    manifest.set_segments(
        [
            {
                "segment_id": "segment-0002",
                "parent_segment_id": None,
                "index": 2,
                "status": "success",
                "start": 10.0,
                "end": 11.0,
                "overlap_previous_seconds": 0,
                "overlap_next_seconds": 0,
                "audio_path": "intermediate/segments/segment-0002.wav",
                "size_bytes": 1,
                "upload_limit_mb": 25,
                "transcription_path": "intermediate/transcription/segment-0002.json",
                "retry_count": 0,
                "error": None,
            },
            {
                "segment_id": "segment-0003a",
                "parent_segment_id": "segment-0003",
                "index": 1,
                "status": "success",
                "start": 0.0,
                "end": 1.0,
                "overlap_previous_seconds": 0,
                "overlap_next_seconds": 0,
                "audio_path": "intermediate/segments/segment-0003a.wav",
                "size_bytes": 1,
                "upload_limit_mb": 25,
                "transcription_path": "intermediate/transcription/segment-0003a.json",
                "retry_count": 0,
                "error": None,
            },
            {
                "segment_id": "segment-0003",
                "parent_segment_id": None,
                "index": 0,
                "status": "superseded",
                "start": 0.0,
                "end": 2.0,
                "overlap_previous_seconds": 0,
                "overlap_next_seconds": 0,
                "audio_path": "intermediate/segments/segment-0003.wav",
                "size_bytes": 1,
                "upload_limit_mb": 25,
                "transcription_path": None,
                "retry_count": 0,
                "error": None,
            },
        ]
    )
    merged = merge_transcriptions(manifest)
    assert [item["text"] for item in merged] == ["first", "second"]
    assert [item["source_segment_id"] for item in merged] == ["segment-0003a", "segment-0002"]
