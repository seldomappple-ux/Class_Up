import json

from class_up.config import AnalysisConfig, AppConfig, MediaConfig, OutputConfig, ProjectConfig, TranscriptionConfig
from class_up.manifest import Manifest
from class_up.transcription.merge import merge_transcriptions, write_m1_outputs
from class_up.transcription.service import transcribe_segments


def test_m1_mock_pipeline_without_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setenv("CLASS_UP_TRANSCRIPTION_API_KEY", "do-not-write-this")
    video = tmp_path / "course.mp4"
    video.write_bytes(b"video")
    config = AppConfig(
        project=ProjectConfig(output_root=str(tmp_path / "outputs")),
        media=MediaConfig(),
        transcription=TranscriptionConfig(provider="mock"),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )
    manifest = Manifest.create(video, tmp_path / "outputs", config)
    segment_audio = manifest.output_dir / "intermediate" / "segments" / "segment-0001.wav"
    segment_audio.parent.mkdir(parents=True, exist_ok=True)
    segment_audio.write_bytes(b"audio")
    manifest.set_duration(12.0)
    manifest.set_segments(
        [
            {
                "segment_id": "segment-0001",
                "parent_segment_id": None,
                "index": 1,
                "status": "ready",
                "start": 0.0,
                "end": 12.0,
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
    transcribe_segments(manifest, config)
    merged = merge_transcriptions(manifest)
    subtitle, transcript = write_m1_outputs(manifest, merged)
    manifest.set_stage("m1", "success")
    manifest.save()

    assert manifest.path.exists()
    assert subtitle.exists()
    assert transcript.exists()
    assert manifest.data["stages"]["m1"]["status"] == "success"
    result_path = manifest.output_dir / manifest.data["segments"][0]["transcription_path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["time_base"] == "segment_relative"
    assert isinstance(result["items"], list)
    assert "do-not-write-this" not in manifest.path.read_text(encoding="utf-8")
