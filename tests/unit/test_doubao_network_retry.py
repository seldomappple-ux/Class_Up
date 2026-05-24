from __future__ import annotations

import pytest

from class_up.config import AnalysisConfig, AppConfig, MediaConfig, OutputConfig, ProjectConfig, TranscriptionConfig, UploadConfig
from class_up.transcription.doubao import DoubaoTranscriptionError, DoubaoTranscriptionService


def _config_for_doubao() -> AppConfig:
    return AppConfig(
        project=ProjectConfig(),
        media=MediaConfig(),
        transcription=TranscriptionConfig(
            provider="doubao",
            endpoint="https://openspeech.bytedance.com",
            api_key_env="CLASS_UP_DOUBAO_API_KEY",
            resource_id="volc.seedasr.auc",
        ),
        upload=UploadConfig(provider="sftp"),
        analysis=AnalysisConfig(),
        output=OutputConfig(),
    )


@pytest.mark.parametrize("exception_name", ["TimeoutException", "TransportError"])
def test_doubao_httpx_network_errors_are_retryable(monkeypatch, exception_name):
    import httpx

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            if exception_name == "TimeoutException":
                raise httpx.TimeoutException("timed out")
            raise httpx.TransportError("network down")

    monkeypatch.setattr(httpx, "Client", FakeClient)
    service = DoubaoTranscriptionService(_config_for_doubao())

    with pytest.raises(DoubaoTranscriptionError) as exc:
        service._submit_and_query("api-key", "request-id", "https://example.com/audio.wav")

    assert exc.value.retryable is True
    assert exception_name in exc.value.code
