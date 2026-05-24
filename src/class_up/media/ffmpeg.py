from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from class_up.manifest import error_info


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOL_PATH_AUDIT_PATH = Path("outputs") / "system" / "tool_path_events.jsonl"
_TOOLS_RECORDED = False
_DOTENV_LOADED = False


class FfmpegError(RuntimeError):
    def __init__(self, message: str, code: str = "FFMPEG_FAILED", detail: str | None = None):
        super().__init__(message)
        self.error = error_info(code, message, detail=detail, retryable=False)


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class MediaDurations:
    format_duration_seconds: float | None
    audio_duration_seconds: float | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _bundled_tool_candidates(tool: str) -> list[Path]:
    exe = f"{tool}.exe" if os.name == "nt" else tool
    candidates = [PROJECT_ROOT / exe, PROJECT_ROOT / "bin" / exe]
    candidates.extend(sorted(PROJECT_ROOT.glob(f"ffmpeg*/bin/{exe}")))
    return candidates


def _ensure_dotenv_loaded() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    _DOTENV_LOADED = True


def resolve_tool_path(tool: str) -> str | None:
    _ensure_dotenv_loaded()
    env_name = f"CLASS_UP_{tool.upper()}_PATH"
    env_path = os.environ.get(env_name, "").strip()
    if env_path:
        path = Path(env_path)
        if path.exists():
            return str(path)
        return None

    for path in _bundled_tool_candidates(tool):
        if path.exists():
            return str(path)

    return shutil.which(tool)


def tool_command(tool: str) -> str:
    path = resolve_tool_path(tool)
    if path is None:
        raise FfmpegError(f"required media tool not found: {tool}", code="FFMPEG_NOT_FOUND")
    return path


def _record_tool_paths(ffmpeg_path: str, ffprobe_path: str) -> None:
    global _TOOLS_RECORDED
    if _TOOLS_RECORDED:
        return
    TOOL_PATH_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": _now_iso(),
        "tool": "ffmpeg",
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_path": ffprobe_path,
        "source": "media.ffmpeg.require_tools",
    }
    with TOOL_PATH_AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _TOOLS_RECORDED = True


def require_tools() -> None:
    paths = {tool: resolve_tool_path(tool) for tool in ("ffmpeg", "ffprobe")}
    missing = [tool for tool, path in paths.items() if path is None]
    if missing:
        raise FfmpegError(f"required media tool not found: {', '.join(missing)}", code="FFMPEG_NOT_FOUND")
    _record_tool_paths(paths["ffmpeg"] or "", paths["ffprobe"] or "")


def run_command(args: list[str]) -> CommandResult:
    completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    result = CommandResult(args=args, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
    if result.returncode != 0:
        raise FfmpegError("ffmpeg command failed", detail=result.stderr[-2000:])
    return result


def probe_duration(video_path: Path) -> float:
    result = run_command(
        [
            tool_command("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def probe_media_durations(path: Path) -> MediaDurations:
    result = run_command(
        [
            tool_command("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,duration",
            "-of",
            "json",
            str(path),
        ]
    )
    data = json.loads(result.stdout)
    format_duration = _optional_float(data.get("format", {}).get("duration"))
    audio_duration: float | None = None
    for stream in data.get("streams", []):
        if isinstance(stream, dict) and stream.get("codec_type") == "audio":
            audio_duration = _optional_float(stream.get("duration"))
            break
    return MediaDurations(format_duration, audio_duration)


def extract_audio(video_path: Path, output_path: Path, sample_rate: int, channels: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            tool_command("ffmpeg"),
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-af",
            "aresample=async=1:first_pts=0",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            str(output_path),
        ]
    )


def cut_audio(source_audio: Path, output_path: Path, start: float, duration: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            tool_command("ffmpeg"),
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source_audio),
            "-c",
            "copy",
            str(output_path),
        ]
    )


def _optional_float(value: object) -> float | None:
    if value in {None, "N/A"}:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
