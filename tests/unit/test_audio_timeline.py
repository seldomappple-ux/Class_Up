from pathlib import Path

from class_up.config import AnalysisConfig, AppConfig, MediaConfig, OutputConfig, ProjectConfig, TranscriptionConfig, UploadConfig
from class_up.manifest import Manifest
from class_up.media import audio, ffmpeg


def _config() -> AppConfig:
    return AppConfig(
        project=ProjectConfig(),
        media=MediaConfig(),
        transcription=TranscriptionConfig(),
        upload=UploadConfig(),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )


def test_extract_audio_enables_ffmpeg_timeline_sync(monkeypatch, tmp_path):
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(ffmpeg, "tool_command", lambda tool: tool)

    def fake_run_command(args):
        captured["args"] = args
        return ffmpeg.CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ffmpeg, "run_command", fake_run_command)

    ffmpeg.extract_audio(tmp_path / "video.mp4", tmp_path / "audio.wav", 16000, 1)

    assert "-af" in captured["args"]
    assert "aresample=async=1:first_pts=0" in captured["args"]


def test_prepare_audio_records_timeline_drift_warning(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    manifest = Manifest.create(video, tmp_path / "outputs", _config())

    monkeypatch.setattr(ffmpeg, "require_tools", lambda: None)
    durations = iter(
        [
            ffmpeg.MediaDurations(format_duration_seconds=100.0, audio_duration_seconds=100.0),
            ffmpeg.MediaDurations(format_duration_seconds=98.5, audio_duration_seconds=98.5),
        ]
    )
    monkeypatch.setattr(ffmpeg, "probe_media_durations", lambda path: next(durations))

    def fake_extract_audio(video_path: Path, output_path: Path, sample_rate: int, channels: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"audio")

    monkeypatch.setattr(ffmpeg, "extract_audio", fake_extract_audio)

    audio.prepare_audio(video, manifest, _config())

    normalized = manifest.data["media"]["normalized_audio"]
    assert normalized["source_audio_duration_seconds"] == 100.0
    assert normalized["normalized_duration_seconds"] == 98.5
    assert normalized["duration_delta_seconds"] == 1.5
    assert normalized["timeline_sync_applied"] is True
    assert manifest.data["reviews"][0]["type"] == "audio_timeline_drift_warning"


def test_ensure_audio_timeline_fills_legacy_manifest(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    manifest = Manifest.create(video, tmp_path / "outputs", _config())
    audio_path = manifest.output_dir / "intermediate" / "audio" / "full_audio.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"audio")
    manifest.set_normalized_audio(audio_path, "wav", 16000, 1)

    monkeypatch.setattr(ffmpeg, "require_tools", lambda: None)
    durations = iter(
        [
            ffmpeg.MediaDurations(format_duration_seconds=100.0, audio_duration_seconds=100.0),
            ffmpeg.MediaDurations(format_duration_seconds=99.9, audio_duration_seconds=99.9),
        ]
    )
    monkeypatch.setattr(ffmpeg, "probe_media_durations", lambda path: next(durations))

    audio.ensure_audio_timeline(video, audio_path, manifest)

    normalized = manifest.data["media"]["normalized_audio"]
    assert normalized["path"] == "intermediate/audio/full_audio.wav"
    assert normalized["source_audio_duration_seconds"] == 100.0
    assert normalized["normalized_duration_seconds"] == 99.9
