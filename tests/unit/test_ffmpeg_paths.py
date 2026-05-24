from __future__ import annotations

import json
from pathlib import Path

from class_up.media import ffmpeg


def test_resolve_tool_path_prefers_bundled_ffmpeg(tmp_path, monkeypatch):
    bundled_dir = tmp_path / "ffmpeg-local" / "bin"
    bundled_dir.mkdir(parents=True)
    ffmpeg_exe = bundled_dir / "ffmpeg.exe"
    ffmpeg_exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(ffmpeg, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ffmpeg, "_DOTENV_LOADED", True)
    monkeypatch.delenv("CLASS_UP_FFMPEG_PATH", raising=False)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda tool: None)

    assert ffmpeg.resolve_tool_path("ffmpeg") == str(ffmpeg_exe)


def test_resolve_tool_path_uses_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "tools" / "ffmpeg.exe"
    custom.parent.mkdir()
    custom.write_text("", encoding="utf-8")

    monkeypatch.setattr(ffmpeg, "_DOTENV_LOADED", True)
    monkeypatch.setenv("CLASS_UP_FFMPEG_PATH", str(custom))

    assert ffmpeg.resolve_tool_path("ffmpeg") == str(custom)


def test_require_tools_records_selected_paths(tmp_path, monkeypatch):
    ffmpeg_exe = tmp_path / "ffmpeg.exe"
    ffprobe_exe = tmp_path / "ffprobe.exe"
    ffmpeg_exe.write_text("", encoding="utf-8")
    ffprobe_exe.write_text("", encoding="utf-8")
    audit_path = tmp_path / "outputs" / "system" / "tool_path_events.jsonl"

    monkeypatch.setattr(ffmpeg, "_DOTENV_LOADED", True)
    monkeypatch.setattr(ffmpeg, "_TOOLS_RECORDED", False)
    monkeypatch.setattr(ffmpeg, "TOOL_PATH_AUDIT_PATH", audit_path)
    monkeypatch.setenv("CLASS_UP_FFMPEG_PATH", str(ffmpeg_exe))
    monkeypatch.setenv("CLASS_UP_FFPROBE_PATH", str(ffprobe_exe))

    ffmpeg.require_tools()

    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_payload["ffmpeg_path"] == str(ffmpeg_exe)
    assert audit_payload["ffprobe_path"] == str(ffprobe_exe)
