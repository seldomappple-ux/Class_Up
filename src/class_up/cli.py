from __future__ import annotations

import argparse
import sys
from pathlib import Path

from class_up.cleanup import preview_cleanup, run_cleanup
from class_up.config import ConfigError, load_config
from class_up.manifest import load_or_create_manifest
from class_up.media.audio import convert_video_to_audio, prepare_audio, segment_audio
from class_up.media.ffmpeg import FfmpegError
from class_up.transcription.merge import merge_transcriptions, write_m1_outputs
from class_up.transcription.service import transcribe_segments


def build_m1_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="class-up", description="Run Class Up M1 transcription pipeline.")
    parser.add_argument("video", type=Path, help="Input video path.")
    parser.add_argument("--config", type=Path, default=Path("config/config.example.yaml"), help="Config YAML path.")
    parser.add_argument("--output-root", type=Path, default=None, help="Override project.output_root.")
    parser.add_argument("--course-title", default=None, help="Output course directory name.")
    parser.add_argument("--resume-manifest", type=Path, default=None, help="Resume from an existing manifest.json.")
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="class-up", description="Class Up backend tools.")
    subparsers = parser.add_subparsers(dest="command")

    m1 = subparsers.add_parser("m1", help="Run M1 transcription pipeline.")
    m1.add_argument("video", type=Path, help="Input video path.")
    m1.add_argument("--config", type=Path, default=Path("config/config.example.yaml"), help="Config YAML path.")
    m1.add_argument("--output-root", type=Path, default=None, help="Override project.output_root.")
    m1.add_argument("--course-title", default=None, help="Output course directory name.")
    m1.add_argument("--resume-manifest", type=Path, default=None, help="Resume from an existing manifest.json.")
    m1.set_defaults(handler=run_m1)

    audio = subparsers.add_parser("audio", help="Convert a video file to an audio file.")
    audio.add_argument("video", type=Path, help="Input video path.")
    audio.add_argument("--output", type=Path, default=None, help="Full output audio file path.")
    audio.add_argument("--output-dir", type=Path, default=None, help="Output directory. Ignored when --output is set.")
    audio.add_argument("--format", default="wav", choices=["wav"], help="Output audio format.")
    audio.add_argument("--sample-rate", type=int, default=16000, help="Output audio sample rate.")
    audio.add_argument("--channels", type=int, default=1, help="Output audio channels.")
    audio.add_argument("--overwrite", action="store_true", help="Overwrite an existing output file.")
    audio.set_defaults(handler=run_audio)

    cleanup = subparsers.add_parser("cleanup", help="Preview or execute layered cleanup.")
    cleanup.add_argument("--config", type=Path, default=Path("config/config.example.yaml"), help="Config YAML path.")
    cleanup.add_argument("--output-root", type=Path, default=None, help="Override project.output_root.")
    cleanup.add_argument("--target", choices=["local", "remote", "all"], default="all", help="Cleanup target.")
    mode = cleanup.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview cleanup without deleting files.")
    mode.add_argument("--execute", action="store_true", help="Execute cleanup.")
    cleanup.add_argument("--reason", default="manual", help="Audit trigger/reason.")
    cleanup.set_defaults(handler=run_cleanup_command)
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


def run_audio(args: argparse.Namespace) -> int:
    try:
        output_path = convert_video_to_audio(
            args.video,
            output_path=args.output,
            output_dir=args.output_dir,
            audio_format=args.format,
            sample_rate=args.sample_rate,
            channels=args.channels,
            overwrite=args.overwrite,
        )
        print(f"Audio written: {output_path}")
        return 0
    except (FfmpegError, ValueError, FileNotFoundError) as exc:
        print(f"Audio conversion failed: {exc}", file=sys.stderr)
        return 1


def run_cleanup_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    output_root = (args.output_root or Path(config.project.output_root)).resolve()
    if args.execute:
        result = run_cleanup(output_root=output_root, cleanup=config.cleanup, upload=config.upload, target=args.target, reason=args.reason)
    else:
        result = preview_cleanup(output_root=output_root, cleanup=config.cleanup, upload=config.upload, target=args.target)
    print(f"Cleanup {'executed' if args.execute else 'preview'}: {result['count']} item(s), estimated_bytes={result['estimated_bytes']}, released_bytes={result['released_bytes']}")
    for item in result["items"]:
        print(f"- {item['target_type']} {item['bytes']} {item['path']} ({item['reason']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in {"m1", "audio", "cleanup", "-h", "--help"}:
        parser = build_m1_parser()
        args = parser.parse_args(argv)
        handler = run_m1
    else:
        parser = build_parser()
        args = parser.parse_args(argv)
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return 0
    try:
        return handler(args)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
