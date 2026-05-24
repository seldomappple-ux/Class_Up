from __future__ import annotations

from fastapi.testclient import TestClient

import class_up.api.app as web_app


def test_cleanup_preview_endpoint_returns_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_app, "OUTPUT_ROOT", tmp_path / "outputs")
    client = TestClient(web_app.app)

    response = client.get("/cleanup/preview")

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert "items" in data


def test_cleanup_run_endpoint_rejects_invalid_target():
    client = TestClient(web_app.app)

    response = client.post("/cleanup/run", data={"target": "bad"})

    assert response.status_code == 400
