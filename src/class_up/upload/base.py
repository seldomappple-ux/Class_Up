from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UploadedAudio:
    public_url: str
    remote_name: str


class UploadService(ABC):
    @abstractmethod
    def upload_audio(self, local_path: Path, remote_name: str) -> UploadedAudio:
        raise NotImplementedError
