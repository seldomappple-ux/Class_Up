import os

import class_up.api.jobs as jobs
from class_up.api.jobs import build_config
from class_up.config import build_config_summary


def test_web_doubao_selection_sets_provider_defaults(monkeypatch):
    monkeypatch.delenv("CLASS_UP_DOUBAO_API_KEY", raising=False)
    config = build_config(api_key="secret-value", provider="doubao")
    assert config.transcription.provider == "doubao"
    assert config.transcription.api_key_env == "CLASS_UP_DOUBAO_API_KEY"
    assert config.transcription.endpoint == "https://openspeech.bytedance.com"
    assert config.transcription.model == "Doubao-录音文件识别2.0"
    assert config.transcription.resource_id == "volc.seedasr.auc"
    assert config.upload.provider == "sftp"
    assert config.transcription_api_key == "secret-value"
    assert "secret-value" not in str(build_config_summary(config))


def test_web_build_config_loads_dotenv_for_upload_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "PROJECT_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "CLASS_UP_UPLOAD_HOST=boneorbit.com",
                "CLASS_UP_UPLOAD_USER=root",
                "CLASS_UP_UPLOAD_KEY_PATH=C:\\Users\\L_W\\.ssh\\id_rsa",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("CLASS_UP_UPLOAD_HOST", raising=False)
    monkeypatch.delenv("CLASS_UP_UPLOAD_USER", raising=False)
    monkeypatch.delenv("CLASS_UP_UPLOAD_KEY_PATH", raising=False)

    config = build_config(api_key="secret-value", provider="doubao")

    assert config.upload.provider == "sftp"
    assert config.transcription_api_key == "secret-value"
    assert os.environ["CLASS_UP_UPLOAD_HOST"] == "boneorbit.com"
    assert os.environ["CLASS_UP_UPLOAD_USER"] == "root"
    assert os.environ["CLASS_UP_UPLOAD_KEY_PATH"] == "C:\\Users\\L_W\\.ssh\\id_rsa"


def test_web_build_config_loads_project_dotenv_when_cwd_differs(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".env").write_text("CLASS_UP_UPLOAD_HOST=project.example.com", encoding="utf-8")
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.setattr(jobs, "PROJECT_ROOT", project_root)
    monkeypatch.chdir(other_cwd)
    monkeypatch.delenv("CLASS_UP_UPLOAD_HOST", raising=False)

    build_config(api_key="secret-value", provider="doubao")

    assert os.environ["CLASS_UP_UPLOAD_HOST"] == "project.example.com"
