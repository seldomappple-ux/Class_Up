from __future__ import annotations

import json
import os
import shutil
import signal
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, FileResponse as FR, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from class_up.api.jobs import UPLOADS_DIR, build_config, find_manifest, list_jobs, run_m1_pipeline
from class_up.manifest import load_or_create_manifest
from class_up.media.audio import convert_video_to_audio

app = FastAPI(title="Class Up")

STATIC_DIR = Path(__file__).parent.parent.parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = Path("outputs")
AUDIO_OUT_DIR = OUTPUT_ROOT / "audio_exports"
API_KEY_AUDIT_PATH = OUTPUT_ROOT / "system" / "api_key_events.jsonl"
PROVIDER_API_KEY_ENVS = {
    "doubao": "CLASS_UP_DOUBAO_API_KEY",
    "remote": "CLASS_UP_TRANSCRIPTION_API_KEY",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _mask_secret(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _project_env_path() -> Path:
    return PROJECT_ROOT / ".env"


def _read_dotenv_map(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _write_dotenv_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out_lines: list[str] = []
    updated = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out_lines.append(f"{key}={value}")
            updated = True
        else:
            out_lines.append(line)
    if not updated:
        if out_lines and out_lines[-1] != "":
            out_lines.append("")
        out_lines.append(f"{key}={value}")
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _append_api_key_audit(provider: str, env_name: str, action: str, value: str) -> None:
    API_KEY_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": _now_iso(),
        "provider": provider,
        "env_name": env_name,
        "action": action,
        "masked_value": _mask_secret(value),
        "length": len(value.strip()),
        "source": "web_ui",
    }
    with API_KEY_AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _resolve_api_key_env(provider: str) -> str:
    env_name = PROVIDER_API_KEY_ENVS.get(provider)
    if not env_name:
        raise HTTPException(status_code=400, detail="provider does not support saved api keys")
    return env_name


def _saved_api_key(provider: str) -> tuple[str, str]:
    env_name = _resolve_api_key_env(provider)
    env_map = _read_dotenv_map(_project_env_path())
    value = os.environ.get(env_name, "").strip() or env_map.get(env_name, "").strip()
    return env_name, value


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    video: UploadFile,
    api_key: str = Form(""),
    provider: str = Form("mock"),
    endpoint: str = Form(""),
    model: str = Form(""),
    course_title: str = Form(""),
    segment_seconds: float = Form(600),
    concurrency: int = Form(3),
):
    if provider == "doubao":
        _, saved_key = _saved_api_key(provider)
        if not api_key.strip() and not saved_key:
            raise HTTPException(status_code=400, detail="閫夋嫨璞嗗寘鏃跺繀椤诲～鍐?API Key")

    upload_id = uuid.uuid4().hex
    upload_dir = UPLOADS_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    video_path = upload_dir / f"video{suffix}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    config = build_config(api_key, provider, endpoint, model, segment_seconds, concurrency)
    manifest = load_or_create_manifest(video_path, OUTPUT_ROOT, config, course_title or None, source_filename=video.filename)
    background_tasks.add_task(run_m1_pipeline, manifest, config)
    return {"task_id": manifest.data["task_id"], "output_dir": str(manifest.output_dir)}


@app.get("/settings/api-key/{provider}")
async def get_saved_api_key(provider: str):
    env_name, value = _saved_api_key(provider)
    return {
        "provider": provider,
        "env_name": env_name,
        "has_value": bool(value),
        "masked_value": _mask_secret(value),
        "audit_path": str(API_KEY_AUDIT_PATH),
    }


@app.post("/settings/api-key")
async def save_api_key(provider: str = Form(...), api_key: str = Form(...)):
    env_name = _resolve_api_key_env(provider)
    value = api_key.strip()
    if not value:
        raise HTTPException(status_code=400, detail="api_key cannot be empty")

    env_path = _project_env_path()
    _write_dotenv_value(env_path, env_name, value)
    os.environ[env_name] = value
    _append_api_key_audit(provider, env_name, "save", value)
    return {
        "provider": provider,
        "env_name": env_name,
        "masked_value": _mask_secret(value),
        "saved_to": str(env_path),
        "audit_path": str(API_KEY_AUDIT_PATH),
    }


@app.get("/jobs")
async def get_jobs():
    return list_jobs()


@app.get("/jobs/{task_id}")
async def get_job(task_id: str):
    m = find_manifest(task_id)
    if not m:
        raise HTTPException(status_code=404, detail="task not found")
    return m.snapshot()


@app.get("/jobs/{task_id}/file/{file_key}")
async def get_file(task_id: str, file_key: str):
    allowed = {"full_subtitle", "full_transcript"}
    if file_key not in allowed:
        raise HTTPException(status_code=400, detail="invalid file_key")
    m = find_manifest(task_id)
    if not m:
        raise HTTPException(status_code=404, detail="task not found")
    rel = m.data["outputs"].get(file_key)
    if not rel:
        raise HTTPException(status_code=404, detail="file not ready")
    path = m.output_dir / rel
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.post("/audio")
async def convert_audio(
    background_tasks: BackgroundTasks,
    video: UploadFile,
    sample_rate: int = Form(16000),
    channels: int = Form(1),
):
    upload_id = uuid.uuid4().hex
    upload_dir = UPLOADS_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    video_path = upload_dir / f"video{suffix}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    stem = Path(video.filename or "audio").stem
    AUDIO_OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = AUDIO_OUT_DIR / f"{upload_id}_{stem}.wav"

    try:
        result = convert_video_to_audio(
            video_path,
            output_path=output_path,
            sample_rate=sample_rate,
            channels=channels,
            overwrite=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"audio_id": upload_id, "filename": result.name}


@app.get("/audio/{audio_id}/download")
async def download_audio(audio_id: str):
    matches = list(AUDIO_OUT_DIR.glob(f"{audio_id}_*.wav"))
    if not matches:
        raise HTTPException(status_code=404, detail="audio not found")
    path = matches[0]
    return FR(path, media_type="audio/wav", filename=path.name)


@app.post("/shutdown")
async def shutdown():
    os.kill(os.getpid(), signal.SIGTERM)
    return {"ok": True}


def _run(mock: bool = False, port: int = 8000) -> None:
    import threading
    import time
    import webbrowser

    import uvicorn

    if mock:
        os.environ["CLASS_UP_TRANSCRIPTION_API_KEY"] = "mock"

    def _open():
        time.sleep(1)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_open, daemon=True).start()
    uvicorn.run("class_up.api.app:app", host="0.0.0.0", port=port, reload=False)


def start() -> None:
    _run(mock=False)


def start_mock() -> None:
    _run(mock=True)
