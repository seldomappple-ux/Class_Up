from __future__ import annotations

import argparse
import sys
from pathlib import Path

from class_up.config import ConfigError, load_config
from class_up.manifest import load_or_create_manifest
from class_up.media.audio import prepare_audio, segment_audio
from class_up.media.ffmpeg import FfmpegError
from class_up.transcription.merge import merge_transcriptions, write_m1_outputs
from class_up.transcription.service import transcribe_segments


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="class-up", description="Run Class Up M1 transcription pipeline.")
    parser.add_argument("video", type=Path, help="Input video path.")
    parser.add_argument("--config", type=Path, default=Path("config/config.example.yaml"), help="Config YAML path.")
    parser.add_argument("--output-root", type=Path, default=None, help="Override project.output_root.")
    parser.add_argument("--course-title", default=None, help="Output course directory name.")
    parser.add_argument("--resume-manifest", type=Path, default=None, help="Resume from an existing manifest.json.")
    return parser


def run_m1(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    output_root = (args.output_root or Path(config.project.output_root)).resolve()
    manifest = load_or_create_manifest(args.video, output_root, config, args.course_title, args.resume_manifest)
    manifest.set_stage("m1", "running")
    manifest.save()
    try:
        if not manifest.data["media"].get("normalized_audio"):
            audio_path = prepare_audio(args.video, manifest, config)
        else:
            audio_path = manifest.output_dir / manifest.data["media"]["normalized_audio"]["path"]
        if not manifest.data["segments"]:
            segment_audio(audio_path, manifest, config)
        transcribe_segments(manifest, config)
        merged = merge_transcriptions(manifest)
        write_m1_outputs(manifest, merged)
        manifest.set_stage("m1", "success")
        manifest.save()
        print(f"M1 completed: {manifest.output_dir}")
        return 0
    except (ConfigError, FfmpegError, Exception) as exc:
        error = getattr(exc, "error", None)
        manifest.set_stage("m1", "failed", error=error)
        if error:
            manifest.add_error(error)
        manifest.save()
        print(f"M1 failed: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_m1(args)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
