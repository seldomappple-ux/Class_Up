from __future__ import annotations

import re
import unicodedata
from typing import Any

from class_up.utils.timecode import seconds_to_srt_time

MAX_SUBTITLE_CHARS = 28
MAX_SUBTITLE_DURATION_SECONDS = 6.0
MIN_SUBTITLE_DURATION_SECONDS = 0.4
WORD_GAP_SPLIT_SECONDS = 0.8
_SENTENCE_SPLIT_RE = re.compile(r"([^。！？!?，,、；;]+[。！？!?，,、；;]?)")
_NORMALIZE_REMOVE_RE = re.compile(r"[\s,，.。、;；:：?？!！\"'“”‘’()\[\]{}<>《》【】\-—_]+")
_SRT_REMOVE_PUNCTUATION = ",，.。、;；"
_SRT_OPTIONAL_PUNCTUATION = "?？!！"


def render_srt(
    items: list[dict[str, Any]],
    clean_punctuation: bool = True,
    keep_question_exclamation: bool = True,
) -> str:
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
            f"{index}\n{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}\n{_srt_text(str(item['text']).strip(), clean_punctuation, keep_question_exclamation)}"
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
        word_gap_items = _split_by_word_gap(item, start, end)
        if word_gap_items is not None:
            split_items.extend(word_gap_items)
            continue
        chunks = _split_text_for_subtitle(text)
        if len(chunks) == 1 and duration > MAX_SUBTITLE_DURATION_SECONDS:
            sentence_chunks = _sentence_chunks(text)
            if len(sentence_chunks) > 1:
                chunks = sentence_chunks
        if len(chunks) == 1 and duration <= MAX_SUBTITLE_DURATION_SECONDS:
            split_items.append({**item, "text": chunks[0]})
            continue
        if len(chunks) > 1 and duration < len(chunks) * MIN_SUBTITLE_DURATION_SECONDS:
            split_items.append(dict(item))
            continue
        split_items.extend(_distribute_time(item, chunks, start, end))
    return split_items


def _split_text_for_subtitle(text: str) -> list[str]:
    sentence_chunks = _sentence_chunks(text)
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


def _sentence_chunks(text: str) -> list[str]:
    return [match.group(0).strip() for match in _SENTENCE_SPLIT_RE.finditer(text) if match.group(0).strip()]


def _split_long_text(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]


def _split_by_word_gap(item: dict[str, Any], start: float, end: float) -> list[dict[str, Any]] | None:
    words = item.get("words")
    if not isinstance(words, list) or len(words) < 2:
        return None
    chunks = _word_gap_chunks(words, start, end)
    if len(chunks) <= 1:
        return None
    results: list[dict[str, Any]] = []
    for index, chunk_words in enumerate(chunks):
        text = _text_from_words(chunk_words)
        if not text:
            return None
        try:
            chunk_start = max(start, min(float(chunk_words[0]["start"]), end))
            chunk_end = max(chunk_start, min(float(chunk_words[-1]["end"]), end))
        except (KeyError, TypeError, ValueError):
            return None
        candidate = {
            **item,
            "start": round(chunk_start, 3),
            "end": round(chunk_end, 3),
            "text": text,
            "source_item_id": item.get("item_id"),
            "split_index": index + 1,
            "split_count": len(chunks),
            "time_estimated": False,
            "time_source": "word",
            "split_reason": "word_gap",
        }
        if not _valid_word_gap_chunk(candidate):
            return None
        results.append(candidate)
    return results


def _word_gap_chunks(words: list[Any], parent_start: float, parent_end: float) -> list[list[dict[str, Any]]]:
    cleaned: list[dict[str, Any]] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        try:
            start = max(parent_start, min(float(word["start"]), parent_end))
            end = max(start, min(float(word["end"]), parent_end))
        except (KeyError, TypeError, ValueError):
            continue
        cleaned.append({**word, "text": text, "start": start, "end": end})
    if len(cleaned) < 2:
        return [cleaned] if cleaned else []
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = [cleaned[0]]
    for previous, current_word in zip(cleaned, cleaned[1:]):
        gap = float(current_word["start"]) - float(previous["end"])
        if gap >= WORD_GAP_SPLIT_SECONDS:
            chunks.append(current)
            current = [current_word]
        else:
            current.append(current_word)
    chunks.append(current)
    return chunks


def _text_from_words(words: list[dict[str, Any]]) -> str:
    return "".join(str(word.get("text") or "").strip() for word in words)


def _valid_word_gap_chunk(chunk: dict[str, Any]) -> bool:
    if float(chunk["end"]) - float(chunk["start"]) < MIN_SUBTITLE_DURATION_SECONDS:
        return False
    text = _srt_text(str(chunk.get("text") or ""), clean_punctuation=True, keep_question_exclamation=False)
    return bool(text)


def _distribute_time(item: dict[str, Any], chunks: list[str], start: float, end: float) -> list[dict[str, Any]]:
    if len(chunks) <= 1:
        return [{**item, "start": start, "end": end, "text": chunks[0] if chunks else str(item["text"]).strip()}]
    word_aligned = _distribute_time_from_words(item, chunks, start, end)
    if word_aligned is not None:
        return word_aligned
    return _distribute_time_estimated(item, chunks, start, end)


def _distribute_time_estimated(item: dict[str, Any], chunks: list[str], start: float, end: float) -> list[dict[str, Any]]:
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
        if index == 0:
            child_start = start
        else:
            child_start = cursor
        if index == len(chunks) - 1:
            child_end = end
        else:
            child_end = chunk_end
        child_start = max(start, min(child_start, end))
        child_end = max(child_start, min(child_end, end))
        if child_end <= child_start:
            break
        results.append(
            {
                **item,
                "start": round(child_start, 3),
                "end": round(child_end, 3),
                "text": chunk,
                "source_item_id": item.get("item_id"),
                "split_index": index + 1,
                "split_count": len(chunks),
                "time_estimated": True,
                "time_source": "estimated",
            }
        )
        cursor = chunk_end
        if cursor >= end:
            break
    if results:
        results[0]["start"] = round(start, 3)
        results[-1]["end"] = round(end, 3)
    return results


def _distribute_time_from_words(item: dict[str, Any], chunks: list[str], start: float, end: float) -> list[dict[str, Any]] | None:
    words = item.get("words")
    if not isinstance(words, list) or not words:
        return None
    matches: list[tuple[int, int]] = []
    cursor = 0
    for chunk in chunks:
        match = _match_chunk_to_words(chunk, words, cursor)
        if match is None:
            return None
        matches.append(match)
        cursor = match[1] + 1

    results: list[dict[str, Any]] = []
    previous_end = start
    for index, (first, last) in enumerate(matches):
        try:
            child_start = float(words[first]["start"])
            child_end = float(words[last]["end"])
        except (KeyError, TypeError, ValueError):
            return None
        child_start = max(start, min(child_start, end))
        child_end = max(child_start, min(child_end, end))
        if index > 0:
            child_start = max(previous_end, child_start)
        if child_end <= child_start:
            return None
        results.append(
            {
                **item,
                "start": round(child_start, 3),
                "end": round(child_end, 3),
                "text": chunks[index],
                "source_item_id": item.get("item_id"),
                "split_index": index + 1,
                "split_count": len(chunks),
                "time_estimated": False,
                "time_source": "word",
            }
        )
        previous_end = child_end
    return results


def _match_chunk_to_words(chunk: str, words: list[Any], start_index: int) -> tuple[int, int] | None:
    target = _normalize_match_text(chunk)
    if not target:
        return None
    first: int | None = None
    combined = ""
    for index in range(start_index, len(words)):
        word = words[index]
        if not isinstance(word, dict):
            continue
        normalized_word = _normalize_match_text(str(word.get("text") or ""))
        if not normalized_word:
            continue
        candidate = combined + normalized_word
        if not target.startswith(candidate):
            return None
        if first is None:
            first = index
        combined = candidate
        if combined == target:
            return (first, index)
    return None


def _normalize_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return _NORMALIZE_REMOVE_RE.sub("", normalized)


def _srt_text(text: str, clean_punctuation: bool, keep_question_exclamation: bool) -> str:
    if not clean_punctuation:
        return text
    remove = _SRT_REMOVE_PUNCTUATION
    if not keep_question_exclamation:
        remove += _SRT_OPTIONAL_PUNCTUATION
    return text.translate(str.maketrans("", "", remove)).strip()
