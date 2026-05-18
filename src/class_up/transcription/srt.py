from __future__ import annotations

from typing import Any

from class_up.utils.timecode import seconds_to_srt_time


def render_srt(items: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    previous_end = 0.0
    for index, item in enumerate(items, start=1):
        start = float(item["start"])
        end = float(item["end"])
        if start < 0 or end < 0:
            raise ValueError("SRT time cannot be negative")
        if end <= start:
            raise ValueError("SRT item end must be greater than start")
        if start < previous_end:
            raise ValueError("SRT time must be monotonic")
        blocks.append(
            f"{index}\n{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}\n{str(item['text']).strip()}"
        )
        previous_end = end
    return "\n\n".join(blocks) + ("\n" if blocks else "")
