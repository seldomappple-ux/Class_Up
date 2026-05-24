from __future__ import annotations

import re
from typing import Any

from class_up.utils.timecode import seconds_to_srt_time

MAX_SUBTITLE_CHARS = 28
MAX_SUBTITLE_DURATION_SECONDS = 6.0
MIN_SUBTITLE_DURATION_SECONDS = 0.4
_SENTENCE_SPLIT_RE = re.compile(r"([^。！？!?，,、；;]+[。！？!?，,、；;]?)")


def render_srt(items: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    previous_end = 0.0
    subtitle_items = split_subtitle_items(items)
    for index, item in enumerate(subtitle_items, start=1):
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


def split_subtitle_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    split_items: list[dict[str, Any]] = []
    for item in items:
        text = str(item["text"]).strip()
        if not text:
            continue
        start = float(item["start"])
        end = float(item["end"])
        duration = end - start
        if duration <= 0:
            split_items.append(dict(item))
            continue
        chunks = _split_text_for_subtitle(text)
        if len(chunks) == 1 and duration <= MAX_SUBTITLE_DURATION_SECONDS:
            split_items.append({**item, "text": chunks[0]})
            continue
        split_items.extend(_distribute_time(item, chunks, start, end))
    return split_items


def _split_text_for_subtitle(text: str) -> list[str]:
    sentence_chunks = [match.group(0).strip() for match in _SENTENCE_SPLIT_RE.finditer(text)]
    if not sentence_chunks:
        sentence_chunks = [text]
    chunks: list[str] = []
    current = ""
    for sentence in sentence_chunks:
        if not sentence:
            continue
        if len(sentence) > MAX_SUBTITLE_CHARS:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(sentence, MAX_SUBTITLE_CHARS))
            continue
        candidate = current + sentence
        if current and len(candidate) > MAX_SUBTITLE_CHARS:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]


def _split_long_text(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]


def _distribute_time(item: dict[str, Any], chunks: list[str], start: float, end: float) -> list[dict[str, Any]]:
    total_chars = sum(max(1, len(chunk)) for chunk in chunks)
    cursor = start
    results: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1:
            chunk_end = end
        else:
            ratio = max(1, len(chunk)) / total_chars
            chunk_duration = max(MIN_SUBTITLE_DURATION_SECONDS, (end - start) * ratio)
            chunk_end = min(end, cursor + chunk_duration)
        if chunk_end <= cursor:
            chunk_end = min(end, cursor + MIN_SUBTITLE_DURATION_SECONDS)
        results.append({**item, "start": round(cursor, 3), "end": round(chunk_end, 3), "text": chunk})
        cursor = chunk_end
        if cursor >= end:
            break
    return results
