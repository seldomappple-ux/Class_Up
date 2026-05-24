from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

import class_up.api.app as web_app


def test_save_api_key_persists_to_env_and_audit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("CLASS_UP_DOUBAO_API_KEY", raising=False)
    client = TestClient(web_app.app)

    response = client.post(
        "/settings/api-key",
        data={"provider": "doubao", "api_key": "secret-abc-1234"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["masked_value"] == "secr...1234"
    assert (tmp_path / ".env").read_text(encoding="utf-8").strip() == "CLASS_UP_DOUBAO_API_KEY=secret-abc-1234"

    audit_path = tmp_path / "outputs" / "system" / "api_key_events.jsonl"
    audit_text = audit_path.read_text(encoding="utf-8")
    assert "secret-abc-1234" not in audit_text
    assert "secr...1234" in audit_text


def test_create_job_allows_saved_api_key_without_retyping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(web_app, "run_m1_pipeline", lambda manifest, config: None)
    monkeypatch.delenv("CLASS_UP_DOUBAO_API_KEY", raising=False)
    (tmp_path / ".env").write_text("CLASS_UP_DOUBAO_API_KEY=secret-abc-1234\n", encoding="utf-8")
    client = TestClient(web_app.app)

    response = client.post(
        "/jobs",
        data={
            "api_key": "",
            "provider": "doubao",
            "endpoint": "",
            "model": "",
            "course_title": "saved-key-course",
            "segment_seconds": "600",
            "concurrency": "2",
        },
        files={"video": ("lesson.mp4", BytesIO(b"fake-video"), "video/mp4")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"]
