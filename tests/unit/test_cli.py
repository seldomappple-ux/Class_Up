from pathlib import Path

from class_up.cli import build_m1_parser, build_parser


def test_audio_command_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["audio", "course.mp4"])
    assert args.video == Path("course.mp4")
    assert args.format == "wav"
    assert args.sample_rate == 16000
    assert args.channels == 1
    assert args.overwrite is False


def test_legacy_m1_parser_still_supported():
    parser = build_m1_parser()
    args = parser.parse_args(["course.mp4", "--course-title", "demo"])
    assert args.video == Path("course.mp4")
    assert args.course_title == "demo"
