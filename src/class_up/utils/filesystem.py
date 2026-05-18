from __future__ import annotations

import re
from pathlib import Path


INVALID_WINDOWS_CHARS = r'<>:"/\\|?*'


def safe_filename(value: str, default: str = "untitled", max_length: int = 120) -> str:
    cleaned = "".join("_" if char in INVALID_WINDOWS_CHARS else char for char in value)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = cleaned.strip(" ._")
    if not cleaned:
        cleaned = default
    return cleaned[:max_length]


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_under_root(root: Path, relative_path: str | Path) -> Path:
    root = root.resolve()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes output root: {relative_path}")
    return target


def relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
