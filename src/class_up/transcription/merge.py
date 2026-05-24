from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from class_up.manifest import Manifest
from class_up.transcription.srt import render_srt
from class_up.utils.filesystem import resolve_under_root, safe_filename


def merge_transcriptions(manifest: Manifest) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    sequence = 1
    timeline = _timeline_correction(manifest)
    successful_segments = [
        segment
        for segment in manifest.data["segments"]
        if segment["status"] == "success" and segment.get("transcription_path")
    ]
    for segment in sorted(successful_segments, key=lambda item: item["index"]):
        path = resolve_under_root(manifest.output_dir, segment["transcription_path"])
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("time_base") != "segment_relative":
            raise ValueError(f"unsupported transcription time_base in {path}")
        for item in result.get("items", []):
            start = timeline.map(round(float(segment["start"]) + float(item["start"]), 3))
            end = timeline.map(round(float(segment["start"]) + float(item["end"]), 3))
            if end <= start:
                continue
            if merged and start < float(merged[-1]["end"]):
                if end <= float(merged[-1]["end"]):
                    continue
                start = float(merged[-1]["end"])
            merged.append(
                {
                    "item_id": f"merged-{sequence:06d}",
                    "source_segment_id": segment["segment_id"],
                    "start": start,
                    "end": end,
                    "text": str(item["text"]).strip(),
                    "overlap_policy": "trim_previous_overlap" if item.get("start", 0) == 0 and sequence > 1 else "none",
                    "timeline_correction_applied": timeline.applied,
                    "timeline_correction_ratio": timeline.ratio,
                }
            )
            sequence += 1
    return merged


def write_m1_outputs(manifest: Manifest, items: list[dict[str, Any]]) -> tuple[Path, Path]:
    source_stem = safe_filename(manifest.data.get("input", {}).get("source_stem") or manifest.data.get("input", {}).get("course_title") or "transcript")
    run_suffix = _output_run_suffix(manifest.output_dir)
    subtitle_path = _unique_output_path(manifest.output_dir / f"{source_stem}_Subtitles{run_suffix}.srt")
    transcript_path = _unique_output_path(manifest.output_dir / f"{source_stem}_text{run_suffix}.txt")
    subtitle_path.write_text(render_srt(items), encoding="utf-8")
    transcript_path.write_text("\n".join(item["text"] for item in items) + ("\n" if items else ""), encoding="utf-8")
    manifest.set_output("full_subtitle", subtitle_path)
    manifest.set_output("full_transcript", transcript_path)
    manifest.save()
    return subtitle_path, transcript_path


class _TimelineCorrection:
    def __init__(self, ratio: float, applied: bool, max_seconds: float | None):
        self.ratio = ratio
        self.applied = applied
        self.max_seconds = max_seconds

    def map(self, seconds: float) -> float:
        mapped = max(0.0, float(seconds) * self.ratio)
        if self.max_seconds is not None:
            mapped = min(mapped, self.max_seconds)
        return round(mapped, 3)


def _timeline_correction(manifest: Manifest) -> _TimelineCorrection:
    normalized = manifest.data.get("media", {}).get("normalized_audio") or {}
    source_duration = _float_or_none(normalized.get("source_audio_duration_seconds"))
    normalized_duration = _float_or_none(normalized.get("normalized_duration_seconds"))
    delta = _float_or_none(normalized.get("duration_delta_seconds"))
    threshold = _float_or_none(normalized.get("timeline_drift_warning_threshold_seconds")) or 0.2
    video_duration = _float_or_none(manifest.data.get("media", {}).get("duration_seconds"))
    if (
        source_duration
        and normalized_duration
        and normalized_duration > 0
        and delta is not None
        and abs(delta) > threshold
    ):
        return _TimelineCorrection(source_duration / normalized_duration, True, video_duration)
    return _TimelineCorrection(1.0, False, video_duration)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _output_run_suffix(output_dir: Path) -> str:
    match = re.search(r"_(\d+)$", output_dir.name)
    return f"_{match.group(1)}" if match else ""


def _unique_output_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
