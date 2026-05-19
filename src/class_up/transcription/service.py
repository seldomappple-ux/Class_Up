from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from class_up.config import AppConfig
from class_up.manifest import Manifest, error_info
from class_up.transcription.base import TranscriptionService
from class_up.transcription.doubao import DoubaoTranscriptionError, DoubaoTranscriptionService
from class_up.utils.filesystem import relative_to_root, resolve_under_root


class MockTranscriptionService(TranscriptionService):
    provider = "mock"

    def __init__(self, model: str = ""):
        self.model = model

    def transcribe(self, segment: dict[str, Any], audio_path: Path) -> dict[str, Any]:
        duration = max(0.1, float(segment["end"]) - float(segment["start"]))
        item_end = round(min(duration, max(0.1, duration - 0.001)), 3)
        return {
            "schema_version": "1.0",
            "segment_id": segment["segment_id"],
            "source_audio": segment["audio_path"],
            "time_base": "segment_relative",
            "language": "zh",
            "provider": self.provider,
            "model": self.model,
            "items": [
                {
                    "item_id": f"{segment['segment_id']}-item-0001",
                    "start": 0.0,
                    "end": item_end,
                    "text": f"模拟转录文本 {segment['segment_id']}",
                    "confidence": None,
                }
            ],
            "raw_output_path": None,
            "error": None,
        }


class UnsupportedTranscriptionService(TranscriptionService):
    def __init__(self, provider: str):
        self.provider = provider

    def transcribe(self, segment: dict[str, Any], audio_path: Path) -> dict[str, Any]:
        raise RuntimeError(f"transcription provider is not implemented: {self.provider}")


def create_transcription_service(config: AppConfig) -> TranscriptionService:
    if config.transcription.provider == "mock":
        return MockTranscriptionService(model=config.transcription.model)
    if config.transcription.provider == "doubao":
        return DoubaoTranscriptionService(config)
    return UnsupportedTranscriptionService(config.transcription.provider)


def transcribe_segments(manifest: Manifest, config: AppConfig, service: TranscriptionService | None = None) -> None:
    service = service or create_transcription_service(config)
    transcription_dir = manifest.output_dir / "intermediate" / "transcription"
    transcription_dir.mkdir(parents=True, exist_ok=True)
    for segment in sorted(manifest.data["segments"], key=lambda item: item["index"]):
        if segment["status"] == "superseded":
            continue
        if segment["status"] == "success" and segment.get("transcription_path"):
            existing = resolve_under_root(manifest.output_dir, segment["transcription_path"])
            if existing.exists():
                continue
        try:
            manifest.update_segment(segment["segment_id"], status="transcribing")
            manifest.save()
            audio_path = resolve_under_root(manifest.output_dir, segment["audio_path"])
            result = service.transcribe(segment, audio_path)
            review = result.pop("_review", None)
            validate_transcription_result(result)
            output_path = transcription_dir / f"{segment['segment_id']}.json"
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            if isinstance(review, dict):
                manifest.add_review(review)
            manifest.update_segment(
                segment["segment_id"],
                status="success",
                transcription_path=relative_to_root(manifest.output_dir, output_path),
                error=None,
            )
        except Exception as exc:
            retryable = True
            if isinstance(exc, DoubaoTranscriptionError):
                retryable = exc.retryable
            failure = error_info(
                "TRANSCRIPTION_FAILED",
                "transcription segment failed",
                detail=str(exc),
                retryable=retryable,
            )
            manifest.update_segment(segment["segment_id"], status="failed", error=failure)
            manifest.add_error(failure)
            raise
        finally:
            manifest.save()


def validate_transcription_result(result: dict[str, Any]) -> None:
    if result.get("schema_version") != "1.0":
        raise ValueError("transcription schema_version must be 1.0")
    if result.get("time_base") != "segment_relative":
        raise ValueError("transcription time_base must be segment_relative")
    items = result.get("items")
    if not isinstance(items, list):
        raise ValueError("transcription items must be a list")
    for item in items:
        if "text" not in item or not str(item["text"]).strip():
            raise ValueError("transcription item text cannot be empty")
        if float(item["end"]) < float(item["start"]):
            raise ValueError("transcription item end cannot be smaller than start")
