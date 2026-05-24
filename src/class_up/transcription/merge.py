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
            start = round(float(segment["start"]) + float(item["start"]), 3)
            end = round(float(segment["start"]) + float(item["end"]), 3)
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
