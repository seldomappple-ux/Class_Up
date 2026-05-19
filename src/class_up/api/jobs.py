from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from class_up.config import (
    AnalysisConfig,
    AppConfig,
    MediaConfig,
    OutputConfig,
    ProjectConfig,
    TranscriptionConfig,
    UploadConfig,
)
from class_up.manifest import Manifest, load_or_create_manifest
from class_up.manifest import error_info
from class_up.media.audio import prepare_audio, segment_audio
from class_up.media.ffmpeg import FfmpegError
from class_up.transcription.merge import merge_transcriptions, write_m1_outputs
from class_up.transcription.service import transcribe_segments

OUTPUT_ROOT = Path("outputs")
UPLOADS_DIR = OUTPUT_ROOT / "uploads"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def build_config(
    api_key: str,
    provider: str = "mock",
    endpoint: str = "",
    model: str = "",
    segment_seconds: float = 600,
    concurrency: int = 3,
    api_key_env: str = "CLASS_UP_TRANSCRIPTION_API_KEY",
) -> AppConfig:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(Path.cwd() / ".env", override=False)
    provider = provider.strip() or "mock"
    if provider == "doubao":
        api_key_env = "CLASS_UP_DOUBAO_API_KEY"
        endpoint = endpoint or "https://openspeech.bytedance.com"
        model = model or "Doubao-\u5f55\u97f3\u6587\u4ef6\u8bc6\u522b2.0"
    if api_key:
        os.environ[api_key_env] = api_key
    elif provider == "mock":
        os.environ.setdefault(api_key_env, "mock")
    return AppConfig(
        project=ProjectConfig(output_root=str(OUTPUT_ROOT)),
        media=MediaConfig(segment_seconds=segment_seconds),
        transcription=TranscriptionConfig(
            provider=provider,
            endpoint=endpoint,
            model=model,
            api_key_env=api_key_env,
            resource_id="volc.seedasr.auc" if provider == "doubao" else "",
            concurrency=concurrency,
        ),
        upload=UploadConfig(provider="sftp" if provider == "doubao" else "none"),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )


def run_m1_pipeline(manifest: Manifest, config: AppConfig) -> None:
    manifest.set_stage("m1", "running")
    manifest.save()
    try:
        video_path = Path(manifest.data["input"]["video_path"])
        if not manifest.data["media"].get("normalized_audio"):
            audio_path = prepare_audio(video_path, manifest, config)
        else:
            audio_path = manifest.output_dir / manifest.data["media"]["normalized_audio"]["path"]
        if not manifest.data["segments"]:
            segment_audio(audio_path, manifest, config)
        transcribe_segments(manifest, config)
        merged = merge_transcriptions(manifest)
        write_m1_outputs(manifest, merged)
        manifest.set_stage("m1", "success")
    except (FfmpegError, Exception) as exc:
        error = getattr(exc, "error", None)
        if error is None:
            error = error_info("M1_PIPELINE_FAILED", "M1 pipeline failed", detail=str(exc), retryable=False)
        manifest.set_stage("m1", "failed", error=error)
        manifest.add_error(error)
    finally:
        manifest.save()


async def start_job(
    video_path: Path,
    api_key: str,
    provider: str = "mock",
    endpoint: str = "",
    model: str = "",
    course_title: str | None = None,
    segment_seconds: float = 600,
    concurrency: int = 3,
) -> dict[str, Any]:
    config = build_config(api_key, provider, endpoint, model, segment_seconds, concurrency)
    manifest = load_or_create_manifest(video_path, OUTPUT_ROOT, config, course_title)
    asyncio.get_event_loop().run_in_executor(None, run_m1_pipeline, manifest, config)
    return {"task_id": manifest.data["task_id"], "output_dir": str(manifest.output_dir)}


def find_manifest(task_id: str) -> Manifest | None:
    for p in OUTPUT_ROOT.rglob("manifest.json"):
        try:
            m = Manifest.load(p)
            if m.data.get("task_id") == task_id:
                return m
        except Exception:
            continue
    return None


def list_jobs() -> list[dict[str, Any]]:
    results = []
    for p in OUTPUT_ROOT.rglob("manifest.json"):
        try:
            m = Manifest.load(p)
            d = m.data
            results.append({
                "task_id": d.get("task_id"),
                "status": d.get("status"),
                "course_title": d.get("input", {}).get("course_title"),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
            })
        except Exception:
            continue
    return sorted(results, key=lambda x: x.get("created_at") or "", reverse=True)
