from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from class_up.config import CleanupConfig, UploadConfig
from class_up.manifest import Manifest, now_iso
from class_up.upload import SftpUploadService


CLEANUP_AUDIT_PATH = Path("outputs") / "system" / "cleanup_events.jsonl"


@dataclass(frozen=True)
class CleanupCandidate:
    target_type: str
    path: str
    reason: str
    bytes: int
    task_id: str | None = None


def build_cleanup_plan(
    output_root: Path = Path("outputs"),
    cleanup: CleanupConfig = CleanupConfig(),
    upload: UploadConfig = UploadConfig(),
    target: str = "all",
    now: datetime | None = None,
    disk_usage_func=shutil.disk_usage,
) -> list[CleanupCandidate]:
    now = now or datetime.now(timezone.utc).astimezone()
    candidates: list[CleanupCandidate] = []
    if target in {"all", "local"}:
        candidates.extend(_local_retention_candidates(output_root, cleanup, now))
        candidates.extend(_disk_pressure_candidates(output_root, cleanup, disk_usage_func))
    if target in {"all", "remote"}:
        candidates.extend(_remote_retention_candidates(upload, cleanup, now))
    return _dedupe_candidates(candidates)


def execute_cleanup_plan(
    candidates: list[CleanupCandidate],
    dry_run: bool = True,
    trigger: str = "manual",
    audit_path: Path = CLEANUP_AUDIT_PATH,
    upload: UploadConfig = UploadConfig(),
) -> dict[str, Any]:
    results = []
    released = 0
    for candidate in candidates:
        success = True
        error = ""
        if not dry_run:
            try:
                if candidate.target_type == "remote_temp_audio":
                    SftpUploadService(upload).delete_audio(Path(candidate.path).name)
                else:
                    _delete_local_path(Path(candidate.path))
                released += candidate.bytes
            except Exception as exc:
                success = False
                error = str(exc) or exc.__class__.__name__
        event = _event(candidate, trigger, dry_run, success, error)
        _append_event(event, audit_path)
        results.append(event)
    return {
        "dry_run": dry_run,
        "count": len(candidates),
        "estimated_bytes": sum(candidate.bytes for candidate in candidates),
        "released_bytes": released,
        "items": [candidate.__dict__ for candidate in candidates],
        "events": results,
    }


def cleanup_remote_audio_record(
    upload_config: UploadConfig,
    remote_audio: dict[str, Any],
    trigger: str = "task_complete",
    audit_path: Path = CLEANUP_AUDIT_PATH,
) -> dict[str, Any]:
    remote_name = str(remote_audio.get("remote_name") or "").strip()
    remote_path = str(remote_audio.get("remote_path") or remote_name).strip()
    candidate = CleanupCandidate(
        target_type="remote_temp_audio",
        path=remote_path,
        reason="task_complete_remote_audio_cleanup",
        bytes=int(remote_audio.get("size_bytes") or 0),
        task_id=None,
    )
    success = True
    error = ""
    try:
        SftpUploadService(upload_config).delete_audio(remote_name)
    except Exception as exc:
        success = False
        error = str(exc) or exc.__class__.__name__
    event = _event(candidate, trigger, False, success, error)
    _append_event(event, audit_path)
    return event


def preview_cleanup(
    output_root: Path = Path("outputs"),
    cleanup: CleanupConfig = CleanupConfig(),
    upload: UploadConfig = UploadConfig(),
    target: str = "all",
) -> dict[str, Any]:
    candidates = build_cleanup_plan(output_root, cleanup, upload, target)
    return execute_cleanup_plan(candidates, dry_run=True, trigger="manual_preview", upload=upload)


def run_cleanup(
    output_root: Path = Path("outputs"),
    cleanup: CleanupConfig = CleanupConfig(),
    upload: UploadConfig = UploadConfig(),
    target: str = "all",
    reason: str = "manual",
) -> dict[str, Any]:
    candidates = build_cleanup_plan(output_root, cleanup, upload, target)
    return execute_cleanup_plan(candidates, dry_run=False, trigger=reason, upload=upload)


def _local_retention_candidates(output_root: Path, cleanup: CleanupConfig, now: datetime) -> list[CleanupCandidate]:
    candidates: list[CleanupCandidate] = []
    for manifest_path in output_root.rglob("manifest.json"):
        try:
            manifest = Manifest.load(manifest_path)
        except Exception:
            continue
        task_id = manifest.data.get("task_id")
        status = str(manifest.data.get("status") or "")
        updated_at = _parse_datetime(str(manifest.data.get("updated_at") or ""))

        video_path = Path(manifest.data.get("input", {}).get("video_path") or "")
        ttl_hours = cleanup.successful_upload_ttl_hours if status == "success" else cleanup.failed_upload_ttl_hours
        if _is_under_uploads(output_root, video_path) and _older_than(video_path, updated_at, now, ttl_hours):
            candidates.append(
                CleanupCandidate("local_uploaded_video", str(video_path), f"{status or 'unknown'}_upload_video_ttl", _path_size(video_path), task_id)
            )

        intermediate = manifest.output_dir / "intermediate"
        if intermediate.exists() and _older_than(intermediate, updated_at, now, cleanup.intermediate_ttl_hours):
            candidates.append(
                CleanupCandidate("local_intermediate_cache", str(intermediate), "intermediate_cache_ttl", _path_size(intermediate), task_id)
            )
    return candidates


def _disk_pressure_candidates(output_root: Path, cleanup: CleanupConfig, disk_usage_func) -> list[CleanupCandidate]:
    usage = disk_usage_func(output_root if output_root.exists() else Path("."))
    min_free = int(cleanup.disk_min_free_gb * 1024 * 1024 * 1024)
    if usage.free >= min_free:
        return []

    candidates: list[CleanupCandidate] = []
    uploads = sorted((path for path in (output_root / "uploads").rglob("video.*") if path.is_file()), key=lambda path: path.stat().st_mtime)
    for path in uploads:
        candidates.append(CleanupCandidate("local_uploaded_video", str(path), "disk_pressure_uploaded_video", path.stat().st_size))

    manifests = []
    for manifest_path in output_root.rglob("manifest.json"):
        try:
            manifests.append(Manifest.load(manifest_path))
        except Exception:
            continue
    manifests.sort(key=lambda manifest: (manifest.output_dir / "intermediate").stat().st_mtime if (manifest.output_dir / "intermediate").exists() else 0)
    for manifest in manifests:
        for rel in ("intermediate/audio", "intermediate/segments", "intermediate/transcription/raw"):
            path = manifest.output_dir / rel
            if path.exists():
                candidates.append(CleanupCandidate("local_intermediate_cache", str(path), f"disk_pressure_{rel}", _path_size(path), manifest.data.get("task_id")))
    return candidates


def _remote_retention_candidates(upload: UploadConfig, cleanup: CleanupConfig, now: datetime) -> list[CleanupCandidate]:
    try:
        import paramiko  # type: ignore
    except ModuleNotFoundError:
        return []
    import os

    host = os.environ.get(upload.host_env, "").strip()
    username = os.environ.get(upload.username_env, "").strip()
    key_path = os.environ.get(upload.private_key_path_env, "").strip()
    if not host or not username or not key_path:
        return []

    remote_dir = upload.remote_dir.rstrip("/")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    candidates: list[CleanupCandidate] = []
    try:
        client.connect(hostname=host, port=upload.port, username=username, key_filename=key_path, timeout=30)
        sftp = client.open_sftp()
        try:
            for attr in sftp.listdir_attr(remote_dir):
                name = attr.filename
                if not _looks_like_remote_segment(name):
                    continue
                mtime = datetime.fromtimestamp(attr.st_mtime, tz=timezone.utc).astimezone()
                if now - mtime >= timedelta(hours=cleanup.remote_audio_ttl_hours):
                    candidates.append(
                        CleanupCandidate(
                            "remote_temp_audio",
                            f"{remote_dir}/{name}",
                            "remote_audio_ttl",
                            int(getattr(attr, "st_size", 0) or 0),
                        )
                    )
        finally:
            sftp.close()
    except Exception:
        return []
    finally:
        client.close()
    return candidates


def _looks_like_remote_segment(name: str) -> bool:
    return name.endswith(".wav") and "_segment-" in name


def _delete_local_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _older_than(path: Path, timestamp: datetime | None, now: datetime, ttl_hours: float) -> bool:
    if not path.exists():
        return False
    base = timestamp or datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone()
    return now - base >= timedelta(hours=ttl_hours)


def _is_under_uploads(output_root: Path, path: Path) -> bool:
    if not path:
        return False
    try:
        path.resolve().relative_to((output_root / "uploads").resolve())
        return True
    except ValueError:
        return False


def _dedupe_candidates(candidates: list[CleanupCandidate]) -> list[CleanupCandidate]:
    seen: set[str] = set()
    result: list[CleanupCandidate] = []
    for candidate in candidates:
        if candidate.path in seen:
            continue
        seen.add(candidate.path)
        result.append(candidate)
    return result


def _event(candidate: CleanupCandidate, trigger: str, dry_run: bool, success: bool, error: str) -> dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "trigger": trigger,
        "dry_run": dry_run,
        "target_type": candidate.target_type,
        "path": candidate.path,
        "reason": candidate.reason,
        "bytes": candidate.bytes,
        "task_id": candidate.task_id,
        "success": success,
        "error": error,
    }


def _append_event(event: dict[str, Any], audit_path: Path) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
