from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from class_up.manifest import error_info


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


def require_tools() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise FfmpegError(f"required media tool not found: {', '.join(missing)}", code="FFMPEG_NOT_FOUND")


def run_command(args: list[str]) -> CommandResult:
    completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    result = CommandResult(args=args, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
    if result.returncode != 0:
        raise FfmpegError("ffmpeg command failed", detail=result.stderr[-2000:])
    return result


def probe_duration(video_path: Path) -> float:
    result = run_command(
        [
            "ffprobe",
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


def extract_audio(video_path: Path, output_path: Path, sample_rate: int, channels: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
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
            "ffmpeg",
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
