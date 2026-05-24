from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from class_up.config import AppConfig, build_config_summary
from class_up.utils.filesystem import ensure_directory, relative_to_root, safe_filename


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def error_info(code: str, message: str, detail: str | None = None, retryable: bool = False) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "occurred_at": now_iso(),
    }
    if detail is not None:
        error["detail"] = detail
    return error


class Manifest:
    def __init__(self, output_dir: Path, data: dict[str, Any]):
        self.output_dir = output_dir
        self.path = output_dir / "manifest.json"
        self.data = data

    @classmethod
    def create(
        cls,
        video_path: Path,
        output_root: Path,
        config: AppConfig,
        course_title: str | None = None,
        source_filename: str | None = None,
    ) -> "Manifest":
        video_path = video_path.resolve()
        source_name = source_filename or video_path.name
        title = safe_filename(course_title or video_path.stem)
        output_dir = ensure_directory(_next_output_dir(output_root, title))
        created_at = now_iso()
        data: dict[str, Any] = {
            "schema_version": "1.0",
            "task_id": f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{title}",
            "created_at": created_at,
            "updated_at": created_at,
            "status": "pending",
            "input": {
                "video_path": str(video_path),
                "video_filename": source_name,
                "source_stem": safe_filename(Path(source_name).stem),
                "course_title": title,
                "metadata": {"lecturer": "", "chapter": "", "tags": []},
            },
            "config_summary": build_config_summary(config),
            "stages": {
                "m1": {"status": "pending", "started_at": None, "finished_at": None, "error": None},
                "m2": {"status": "pending", "started_at": None, "finished_at": None, "error": None},
                "m3": {"status": "pending", "started_at": None, "finished_at": None, "error": None},
            },
            "media": {
                "duration_seconds": None,
                "source_video": {
                    "path": str(video_path),
                    "format": video_path.suffix.lstrip(".").lower(),
                    "size_bytes": video_path.stat().st_size if video_path.exists() else None,
                    "sha256": file_sha256(video_path) if video_path.exists() else None,
                },
                "normalized_audio": None,
            },
            "segments": [],
            "outputs": {
                "full_subtitle": None,
                "full_transcript": None,
                "knowledge_points": None,
                "knowledge_base": None,
                "clips_root": None,
            },
            "clips": [],
            "reviews": [],
            "errors": [],
        }
        return cls(output_dir, data)

    @classmethod
    def load(cls, manifest_path: Path) -> "Manifest":
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls(manifest_path.parent, data)

    def save(self) -> None:
        self.data["updated_at"] = now_iso()
        ensure_directory(self.output_dir)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.data)

    def set_stage(self, stage: str, status: str, error: dict[str, Any] | None = None) -> None:
        stage_data = self.data["stages"][stage]
        old_status = stage_data["status"]
        stage_data["status"] = status
        if status == "running" and old_status != "running":
            stage_data["started_at"] = now_iso()
        if status in {"success", "failed", "skipped"}:
            stage_data["finished_at"] = now_iso()
        stage_data["error"] = error
        self._sync_status()

    def _sync_status(self) -> None:
        stages = self.data["stages"]
        if any(stage["status"] == "running" for stage in stages.values()):
            self.data["status"] = "running"
        elif any(stage["status"] == "failed" for stage in stages.values()):
            self.data["status"] = "failed"
        elif all(stage["status"] == "success" for stage in stages.values()):
            self.data["status"] = "success"
        elif stages["m1"]["status"] == "success" and stages["m2"]["status"] == "pending":
            self.data["status"] = "success"
        else:
            self.data["status"] = "pending"

    def add_error(self, error: dict[str, Any]) -> None:
        self.data["errors"].append(error)

    def add_review(self, review: dict[str, Any]) -> None:
        self.data["reviews"].append(review)

    def set_duration(self, duration_seconds: float) -> None:
        self.data["media"]["duration_seconds"] = duration_seconds

    def set_normalized_audio(self, path: Path, audio_format: str, sample_rate: int, channels: int) -> None:
        self.data["media"]["normalized_audio"] = {
            "path": relative_to_root(self.output_dir, path),
            "format": audio_format,
            "sample_rate": sample_rate,
            "channels": channels,
            "size_bytes": path.stat().st_size if path.exists() else None,
        }

    def set_segments(self, segments: list[dict[str, Any]]) -> None:
        self.data["segments"] = segments

    def update_segment(self, segment_id: str, **updates: Any) -> None:
        for segment in self.data["segments"]:
            if segment["segment_id"] == segment_id:
                segment.update(updates)
                return
        raise KeyError(f"segment not found: {segment_id}")

    def set_output(self, key: str, path: Path) -> None:
        self.data["outputs"][key] = relative_to_root(self.output_dir, path)


def load_or_create_manifest(
    video_path: Path,
    output_root: Path,
    config: AppConfig,
    course_title: str | None = None,
    resume_manifest: Path | None = None,
    source_filename: str | None = None,
) -> Manifest:
    if resume_manifest and resume_manifest.exists():
        return Manifest.load(resume_manifest)
    manifest = Manifest.create(video_path, output_root, config, course_title, source_filename)
    manifest.save()
    return manifest


def _next_output_dir(output_root: Path, title: str) -> Path:
    base = (output_root / title).resolve()
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = (output_root / f"{title}_{counter}").resolve()
        if not candidate.exists():
            return candidate
        counter += 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
