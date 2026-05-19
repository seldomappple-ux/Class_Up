from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from class_up.config import AppConfig
from class_up.manifest import Manifest, error_info
from class_up.media import ffmpeg
from class_up.utils.filesystem import relative_to_root


LETTERS = "abcdefghijklmnopqrstuvwxyz"


def convert_video_to_audio(
    video_path: Path,
    output_path: Path | None = None,
    output_dir: Path | None = None,
    audio_format: str = "wav",
    sample_rate: int = 16000,
    channels: int = 1,
    overwrite: bool = False,
) -> Path:
    if audio_format != "wav":
        raise ValueError("only wav output is supported in the current backend")
    video_path = video_path.resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"input video not found: {video_path}")
    if output_path and output_dir:
        raise ValueError("--output and --output-dir cannot be used together")
    if output_path is None:
        base_dir = output_dir.resolve() if output_dir else video_path.parent
        output_path = base_dir / f"{video_path.stem}.{audio_format}"
    else:
        output_path = output_path.resolve()
    if output_path.exists() and not overwrite:
        raise ValueError(f"output file already exists, use --overwrite: {output_path}")
    ffmpeg.require_tools()
    ffmpeg.extract_audio(video_path, output_path, sample_rate, channels)
    return output_path


def prepare_audio(video_path: Path, manifest: Manifest, config: AppConfig) -> Path:
    ffmpeg.require_tools()
    duration = ffmpeg.probe_duration(video_path)
    manifest.set_duration(duration)
    audio_path = manifest.output_dir / "intermediate" / "audio" / f"full_audio.{config.media.audio_format}"
    ffmpeg.extract_audio(video_path, audio_path, config.media.audio_sample_rate, config.media.audio_channels)
    manifest.set_normalized_audio(
        audio_path,
        config.media.audio_format,
        config.media.audio_sample_rate,
        config.media.audio_channels,
    )
    manifest.save()
    return audio_path


def planned_ranges(duration: float, segment_seconds: float, overlap_seconds: float) -> list[tuple[float, float, float, float]]:
    ranges: list[tuple[float, float, float, float]] = []
    cursor = 0.0
    while cursor < duration:
        end = min(duration, cursor + segment_seconds)
        overlap_previous = 0.0 if not ranges else overlap_seconds
        overlap_next = overlap_seconds if end < duration else 0.0
        ranges.append((cursor, end, overlap_previous, overlap_next))
        if end >= duration:
            break
        cursor = max(0.0, end - overlap_seconds)
    return ranges


def segment_audio(audio_path: Path, manifest: Manifest, config: AppConfig) -> list[dict[str, Any]]:
    duration = float(manifest.data["media"]["duration_seconds"])
    raw_segments: list[dict[str, Any]] = []
    max_bytes = int(config.transcription.upload_limit_mb * 1024 * 1024)
    for position, (start, end, overlap_previous, overlap_next) in enumerate(
        planned_ranges(duration, config.media.segment_seconds, config.media.overlap_seconds),
        start=1,
    ):
        segment_id = f"segment-{position:04d}"
        raw_segments.extend(
            _cut_with_size_limit(
                audio_path,
                manifest,
                segment_id,
                start,
                end,
                overlap_previous,
                overlap_next,
                max_bytes,
                config.transcription.upload_limit_mb,
            )
        )
    ready_segments = [segment for segment in raw_segments if segment["status"] != "superseded"]
    ready_segments.sort(key=lambda segment: (segment["start"], segment["end"], segment["segment_id"]))
    for index, segment in enumerate(ready_segments, start=1):
        segment["index"] = index
    all_segments = ready_segments + [segment for segment in raw_segments if segment["status"] == "superseded"]
    manifest.set_segments(all_segments)
    manifest.save()
    return all_segments


def _cut_with_size_limit(
    audio_path: Path,
    manifest: Manifest,
    segment_id: str,
    start: float,
    end: float,
    overlap_previous: float,
    overlap_next: float,
    max_bytes: int,
    upload_limit_mb: float,
    attempt: int = 0,
    parent_segment_id: str | None = None,
) -> list[dict[str, Any]]:
    segment_path = manifest.output_dir / "intermediate" / "segments" / f"{segment_id}.wav"
    ffmpeg.cut_audio(audio_path, segment_path, start, end - start)
    size = segment_path.stat().st_size
    base_record = _segment_record(
        manifest,
        segment_id,
        parent_segment_id,
        start,
        end,
        overlap_previous,
        overlap_next,
        segment_path,
        size,
        upload_limit_mb,
    )
    if size <= max_bytes:
        return [base_record]
    if attempt >= 2:
        base_record["status"] = "failed"
        base_record["error"] = error_info(
            "SEGMENT_TOO_LARGE",
            "audio segment exceeds upload limit after re-splitting",
            detail=f"segment_id={segment_id}, size_bytes={size}, limit_bytes={max_bytes}",
            retryable=False,
        )
        return [base_record]
    midpoint = start + (end - start) / 2
    parent = dict(base_record)
    parent["status"] = "superseded"
    parent["error"] = None
    children: list[dict[str, Any]] = [parent]
    suffixes = LETTERS[:2] if parent_segment_id is None else [LETTERS[attempt * 2], LETTERS[attempt * 2 + 1]]
    for suffix, child_start, child_end in (
        (suffixes[0], start, midpoint),
        (suffixes[1], midpoint, end),
    ):
        children.extend(
            _cut_with_size_limit(
                audio_path,
                manifest,
                f"{segment_id}{suffix}",
                child_start,
                child_end,
                overlap_previous if math.isclose(child_start, start) else 0.0,
                overlap_next if math.isclose(child_end, end) else 0.0,
                max_bytes,
                upload_limit_mb,
                attempt + 1,
                parent_segment_id=segment_id,
            )
        )
    return children


def _segment_record(
    manifest: Manifest,
    segment_id: str,
    parent_segment_id: str | None,
    start: float,
    end: float,
    overlap_previous: float,
    overlap_next: float,
    audio_path: Path,
    size_bytes: int,
    upload_limit_mb: float,
) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "parent_segment_id": parent_segment_id,
        "index": 0,
        "status": "ready",
        "start": round(start, 3),
        "end": round(end, 3),
        "overlap_previous_seconds": overlap_previous,
        "overlap_next_seconds": overlap_next,
        "audio_path": relative_to_root(manifest.output_dir, audio_path),
        "size_bytes": size_bytes,
        "upload_limit_mb": upload_limit_mb,
        "transcription_path": None,
        "retry_count": 0,
        "error": None,
    }
