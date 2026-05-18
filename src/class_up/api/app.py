from __future__ import annotations

import os
import shutil
import signal
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from class_up.api.jobs import UPLOADS_DIR, find_manifest, list_jobs, run_m1_pipeline, build_config
from class_up.manifest import load_or_create_manifest

app = FastAPI(title="Class Up")

STATIC_DIR = Path(__file__).parent.parent.parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

OUTPUT_ROOT = Path("outputs")


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
    upload_id = uuid.uuid4().hex
    upload_dir = UPLOADS_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    video_path = upload_dir / f"video{suffix}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    config = build_config(api_key, provider, endpoint, model, segment_seconds, concurrency)
    manifest = load_or_create_manifest(video_path, OUTPUT_ROOT, config, course_title or None)
    background_tasks.add_task(run_m1_pipeline, manifest, config)
    return {"task_id": manifest.data["task_id"], "output_dir": str(manifest.output_dir)}


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
