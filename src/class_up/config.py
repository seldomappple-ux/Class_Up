from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectConfig:
    output_root: str = "outputs"


@dataclass(frozen=True)
class MediaConfig:
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_format: str = "wav"
    segment_seconds: float = 600
    overlap_seconds: float = 30


@dataclass(frozen=True)
class TranscriptionConfig:
    provider: str = "mock"
    endpoint: str = ""
    model: str = ""
    auth_type: str = "api_key"
    api_key_env: str = "CLASS_UP_TRANSCRIPTION_API_KEY"
    resource_id: str = ""
    upload_limit_mb: float = 25
    concurrency: int = 3
    timeout_seconds: int = 120
    max_retries: int = 3
    poll_interval_seconds: int = 1
    max_poll_seconds: int = 600
    request: dict[str, Any] | None = None


@dataclass(frozen=True)
class UploadConfig:
    provider: str = "none"
    host_env: str = "CLASS_UP_UPLOAD_HOST"
    port: int = 22
    username_env: str = "CLASS_UP_UPLOAD_USER"
    private_key_path_env: str = "CLASS_UP_UPLOAD_KEY_PATH"
    remote_dir: str = "/var/www/class-up/audio/"
    public_url_base: str = "https://boneorbit.com/class-up/audio/"


@dataclass(frozen=True)
class AnalysisConfig:
    provider: str = "mock"
    endpoint: str = ""
    model: str = ""
    auth_type: str = "api_key"
    api_key_env: str = "CLASS_UP_ANALYSIS_API_KEY"
    timeout_seconds: int = 180
    max_retries: int = 2


@dataclass(frozen=True)
class OutputConfig:
    keep_intermediate: bool = True
    overwrite: bool = False


@dataclass(frozen=True)
class AppConfig:
    project: ProjectConfig
    media: MediaConfig
    transcription: TranscriptionConfig
    upload: UploadConfig
    analysis: AnalysisConfig
    output: OutputConfig

    @property
    def transcription_api_key(self) -> str | None:
        return os.environ.get(self.transcription.api_key_env)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise ConfigError("PyYAML is required to read YAML config files. Install with: pip install -e .") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError("config file must contain a YAML object")
    return data


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"config section '{name}' must be an object")
    return value


def _endpoint_host(endpoint: str) -> str:
    if not endpoint:
        return ""
    parsed = urlparse(endpoint)
    return parsed.netloc or parsed.path.split("/")[0]


def load_config(config_path: str | Path, dotenv_path: str | Path | None = None) -> AppConfig:
    config_path = Path(config_path)
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")
    _load_dotenv(Path(dotenv_path) if dotenv_path else config_path.parent.parent / ".env")
    data = _read_yaml(config_path)
    config = AppConfig(
        project=ProjectConfig(**_section(data, "project")),
        media=MediaConfig(**_section(data, "media")),
        transcription=TranscriptionConfig(**_section(data, "transcription")),
        upload=UploadConfig(**_section(data, "upload")),
        analysis=AnalysisConfig(**_section(data, "analysis")),
        output=OutputConfig(**_section(data, "output")),
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if config.media.segment_seconds <= 0:
        raise ConfigError("media.segment_seconds must be greater than 0")
    if config.media.overlap_seconds < 0:
        raise ConfigError("media.overlap_seconds cannot be negative")
    if config.media.segment_seconds <= config.media.overlap_seconds:
        raise ConfigError("media.segment_seconds must be greater than media.overlap_seconds")
    if config.transcription.concurrency < 1:
        raise ConfigError("transcription.concurrency must be greater than or equal to 1")
    if config.transcription.upload_limit_mb <= 0:
        raise ConfigError("transcription.upload_limit_mb must be greater than 0")
    if config.transcription.poll_interval_seconds < 1:
        raise ConfigError("transcription.poll_interval_seconds must be greater than or equal to 1")
    if config.transcription.max_poll_seconds < config.transcription.poll_interval_seconds:
        raise ConfigError("transcription.max_poll_seconds must be greater than or equal to poll_interval_seconds")
    if config.upload.provider not in {"none", "sftp"}:
        raise ConfigError("upload.provider must be one of: none, sftp")
    if config.upload.port < 1:
        raise ConfigError("upload.port must be greater than or equal to 1")


def build_config_summary(config: AppConfig) -> dict[str, Any]:
    return {
        "media": vars(config.media),
        "transcription": {
            "provider": config.transcription.provider,
            "endpoint_host": _endpoint_host(config.transcription.endpoint),
            "model": config.transcription.model,
            "auth_type": config.transcription.auth_type,
            "api_key_env": config.transcription.api_key_env,
            "resource_id": config.transcription.resource_id,
            "upload_limit_mb": config.transcription.upload_limit_mb,
            "concurrency": config.transcription.concurrency,
            "timeout_seconds": config.transcription.timeout_seconds,
            "max_retries": config.transcription.max_retries,
            "poll_interval_seconds": config.transcription.poll_interval_seconds,
            "max_poll_seconds": config.transcription.max_poll_seconds,
        },
        "upload": {
            "provider": config.upload.provider,
            "host_env": config.upload.host_env,
            "port": config.upload.port,
            "username_env": config.upload.username_env,
            "private_key_path_env": config.upload.private_key_path_env,
            "remote_dir": config.upload.remote_dir,
            "public_url_base": config.upload.public_url_base,
        },
        "analysis": {
            "provider": config.analysis.provider,
            "endpoint_host": _endpoint_host(config.analysis.endpoint),
            "model": config.analysis.model,
            "auth_type": config.analysis.auth_type,
            "api_key_env": config.analysis.api_key_env,
            "timeout_seconds": config.analysis.timeout_seconds,
            "max_retries": config.analysis.max_retries,
        },
    }
