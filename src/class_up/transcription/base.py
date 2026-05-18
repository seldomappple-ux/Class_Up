from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class TranscriptionService(ABC):
    provider: str

    @abstractmethod
    def transcribe(self, segment: dict[str, Any], audio_path: Path) -> dict[str, Any]:
        raise NotImplementedError
