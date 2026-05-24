from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from class_up.config import AppConfig
from class_up.manifest import now_iso
from class_up.transcription.base import TranscriptionService
from class_up.upload import SftpUploadService, UploadService
from class_up.utils.filesystem import relative_to_root, safe_filename

SUCCESS_CODE = "20000000"
PENDING_CODES = {"20000001", "20000002"}
RETRYABLE_CODES = {"45000131", "55000031"}


class DoubaoTranscriptionError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(f"doubao transcription failed: {code} {message}".strip())
        self.code = code
        self.retryable = retryable


class DoubaoTranscriptionService(TranscriptionService):
    provider = "doubao"

    def __init__(self, config: AppConfig, upload_service: UploadService | None = None):
        self.config = config
        self.upload_service = upload_service or SftpUploadService(config.upload)

    def transcribe(self, segment: dict[str, Any], audio_path: Path) -> dict[str, Any]:
        api_key = self.config.transcription_api_key
        if not api_key:
            raise ValueError(f"missing Doubao API key env: {self.config.transcription.api_key_env}")
        if self.config.upload.provider != "sftp":
            raise ValueError("Doubao provider requires upload.provider=sftp")

        output_dir = audio_path.parents[2]
        remote_name = _remote_audio_name(output_dir.name, segment["segment_id"], audio_path.suffix)
        uploaded = self.upload_service.upload_audio(audio_path, remote_name)
        request_id = uuid.uuid4().hex
        raw = self._submit_and_query(api_key, request_id, uploaded.public_url)

        raw_dir = output_dir / "intermediate" / "transcription" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{segment['segment_id']}.doubao.json"
        raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

        result = convert_doubao_result(
            segment=segment,
            doubao_body=raw["query"]["body"],
            model=self.config.transcription.model or "bigmodel",
            raw_output_path=relative_to_root(output_dir, raw_path),
        )
        return result

    def _submit_and_query(self, api_key: str, request_id: str, audio_url: str) -> dict[str, Any]:
        try:
            import httpx  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("httpx is required for Doubao transcription. Install with: pip install -e .") from exc

        endpoint = (self.config.transcription.endpoint or "https://openspeech.bytedance.com").rstrip("/")
        submit_url = f"{endpoint}/api/v3/auc/bigmodel/submit"
        query_url = f"{endpoint}/api/v3/auc/bigmodel/query"
        resource_id = self.config.transcription.resource_id or "volc.seedasr.auc"
        timeout = self.config.transcription.timeout_seconds
        base_headers = {
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": request_id,
        }
        payload = {
            "user": {"uid": "class-up"},
            "audio": {
                "url": audio_url,
                "format": "wav",
                "codec": "raw",
                "rate": self.config.media.audio_sample_rate,
                "bits": 16,
                "channel": self.config.media.audio_channels,
            },
            "request": self._request_payload(),
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                submit_headers = dict(base_headers)
                submit_headers["X-Api-Sequence"] = "-1"
                submit_response = client.post(submit_url, headers=submit_headers, json=payload)
                submit_meta = _safe_response_meta(submit_response)
                submit_code = submit_response.headers.get("X-Api-Status-Code", "")
                if submit_code != SUCCESS_CODE:
                    raise DoubaoTranscriptionError(
                        submit_code,
                        submit_response.headers.get("X-Api-Message", ""),
                        _is_retryable(submit_code),
                    )

                deadline = time.monotonic() + self.config.transcription.max_poll_seconds
                query_meta: dict[str, Any] | None = None
                query_body: dict[str, Any] = {}
                while time.monotonic() <= deadline:
                    query_response = client.post(query_url, headers=base_headers, json={})
                    query_meta = _safe_response_meta(query_response)
                    query_code = query_response.headers.get("X-Api-Status-Code", "")
                    if query_code == SUCCESS_CODE:
                        query_body = _json_body(query_response)
                        return {
                            "request_id": request_id,
                            "submitted_at": now_iso(),
                            "audio_url": audio_url,
                            "submit": submit_meta,
                            "query": {**query_meta, "body": query_body},
                        }
                    if query_code in PENDING_CODES:
                        time.sleep(self.config.transcription.poll_interval_seconds)
                        continue
                    raise DoubaoTranscriptionError(
                        query_code,
                        query_response.headers.get("X-Api-Message", ""),
                        _is_retryable(query_code),
                    )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            detail = str(exc) or exc.__class__.__name__
            raise DoubaoTranscriptionError(exc.__class__.__name__, detail, retryable=True) from exc

        raise DoubaoTranscriptionError("TRANSCRIPTION_TIMEOUT", "Doubao query timed out", retryable=True)

    def _request_payload(self) -> dict[str, Any]:
        request = dict(self.config.transcription.request or {})
        request.setdefault("model_name", _doubao_api_model_name(self.config.transcription.model))
        request.setdefault("enable_itn", True)
        request.setdefault("enable_punc", True)
        request.setdefault("show_utterances", True)
        request.setdefault("vad_segment", True)
        return request


def convert_doubao_result(
    segment: dict[str, Any],
    doubao_body: dict[str, Any],
    model: str,
    raw_output_path: str,
) -> dict[str, Any]:
    result = doubao_body.get("result") if isinstance(doubao_body, dict) else None
    if not isinstance(result, dict):
        raise ValueError("Doubao response missing result object")

    items: list[dict[str, Any]] = []
    utterances = result.get("utterances")
    if isinstance(utterances, list):
        for idx, utterance in enumerate(utterances, start=1):
            if not isinstance(utterance, dict):
                continue
            text = str(utterance.get("text") or "").strip()
            if not text:
                continue
            start = round(float(utterance.get("start_time", 0)) / 1000, 3)
            end = round(float(utterance.get("end_time", 0)) / 1000, 3)
            items.append(_item(segment["segment_id"], idx, start, end, text))

    fallback_review: dict[str, Any] | None = None
    if not items:
        text = str(result.get("text") or "").strip()
        if not text:
            raise ValueError("Doubao response contains no transcription text")
        duration = max(0.1, float(segment["end"]) - float(segment["start"]))
        items.append(_item(segment["segment_id"], 1, 0.0, round(duration, 3), text))
        fallback_review = {
            "type": "transcription_timestamp_fallback",
            "segment_id": segment["segment_id"],
            "created_at": now_iso(),
            "message": "Doubao response did not include utterances; generated one segment-wide item.",
        }

    internal = {
        "schema_version": "1.0",
        "segment_id": segment["segment_id"],
        "source_audio": segment["audio_path"],
        "time_base": "segment_relative",
        "language": "zh",
        "provider": "doubao",
        "model": model,
        "items": items,
        "raw_output_path": raw_output_path,
        "error": None,
    }
    if fallback_review:
        internal["_review"] = fallback_review
    return internal


def _item(segment_id: str, idx: int, start: float, end: float, text: str) -> dict[str, Any]:
    if end < start:
        raise ValueError("Doubao utterance end_time cannot be smaller than start_time")
    return {
        "item_id": f"{segment_id}-item-{idx:04d}",
        "start": start,
        "end": end,
        "text": text,
        "confidence": None,
    }


def _remote_audio_name(task_name: str, segment_id: str, suffix: str) -> str:
    suffix = suffix if suffix.startswith(".") else ".wav"
    return f"{safe_filename(task_name)}_{safe_filename(segment_id)}{suffix or '.wav'}"


def _safe_response_meta(response: Any) -> dict[str, Any]:
    headers = response.headers
    return {
        "http_status": response.status_code,
        "x_api_status_code": headers.get("X-Api-Status-Code", ""),
        "x_api_message": headers.get("X-Api-Message", ""),
        "x_tt_logid": headers.get("X-Tt-Logid", ""),
    }


def _json_body(response: Any) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _is_retryable(code: str) -> bool:
    return code in RETRYABLE_CODES or code.startswith("550")


def _doubao_api_model_name(model: str) -> str:
    if not model:
        return "bigmodel"
    if model == "Doubao-录音文件识别2.0":
        return "bigmodel"
    if "录音文件识别" in model:
        return "bigmodel"
    return model
