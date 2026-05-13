from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from subscription_bridge.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "providers" in data
    assert "fake" in data["providers"]


def test_ask_fake(client: TestClient) -> None:
    response = client.post("/ask", json={"prompt": "Say hello", "provider": "fake"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Hello" in data["text"]


def test_ask_fake_json_mode(client: TestClient) -> None:
    response = client.post("/ask", json={
        "prompt": "Return JSON with project info",
        "provider": "fake",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_ask_missing_prompt(client: TestClient) -> None:
    response = client.post("/ask", json={"provider": "fake"})
    assert response.status_code == 422  # validation error


def test_ask_unknown_provider(client: TestClient) -> None:
    response = client.post("/ask", json={
        "prompt": "hello", "provider": "nonexistent",
    })
    assert response.status_code == 404


def test_ask_with_files(client: TestClient, tmp_path: Path) -> None:
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    response = client.post("/ask", json={
        "prompt": "read this file",
        "provider": "fake",
        "files": [str(f)],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_run_fake(client: TestClient) -> None:
    response = client.post("/run", json={
        "task": "test task",
        "provider": "fake",
        "workspace": ".",
        "max_steps": 10,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True or data["success"] is False
    assert "run_id" in data


def test_sessions(client: TestClient) -> None:
    response = client.get("/sessions")
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data


def test_codebase_index(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    return 42\n")
    response = client.post("/codebase/index", json={"workspace": str(tmp_path)})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["file_count"] >= 1


def test_codebase_search_before_index(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/codebase/search", json={
        "workspace": str(tmp_path),
        "query": "hello",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["indexed"] is False
    assert "No codebase index found" in (data.get("error") or "")


def test_codebase_search_after_index(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("def hello():\n    return 42\n")
    client.post("/codebase/index", json={"workspace": str(tmp_path)})

    response = client.post("/codebase/search", json={
        "workspace": str(tmp_path),
        "query": "hello",
        "top_k": 5,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["indexed"] is True


def test_codebase_stats_no_index(client: TestClient, tmp_path: Path) -> None:
    response = client.get(f"/codebase/stats?workspace={tmp_path}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


def test_codebase_stats_after_index(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    client.post("/codebase/index", json={"workspace": str(tmp_path)})

    response = client.get(f"/codebase/stats?workspace={tmp_path}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["file_count"] >= 1


def test_run_fake_invalid_provider(client: TestClient) -> None:
    response = client.post("/run", json={
        "task": "test",
        "provider": "nonexistent",
    })
    assert response.status_code == 404


def test_error_response_structured(client: TestClient) -> None:
    response = client.post("/ask", json={
        "prompt": "test",
        "provider": "nonexistent",
    })
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
