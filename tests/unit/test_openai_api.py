from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from subscription_bridge.api.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_v1_models(client: TestClient) -> None:
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1
    model_ids = [m["id"] for m in data["data"]]
    assert "subscription-bridge-fake" in model_ids


def test_v1_models_shape(client: TestClient) -> None:
    response = client.get("/v1/models")
    data = response.json()
    model = data["data"][0]
    assert model["object"] == "model"
    assert model["owned_by"] == "subscription-bridge"
    assert "created" in model


def test_v1_chat_completion_fake(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "Say hello"}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert len(data["choices"]) > 0
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert len(data["choices"][0]["message"]["content"]) > 0
    assert data["choices"][0]["finish_reason"] == "stop"


def test_v1_chat_completion_with_system(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Say hello"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] is not None


def test_v1_unknown_model(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-unknown",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "not found" in data["error"]["message"].lower()


def test_v1_missing_messages(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"model": "subscription-bridge-fake"},
    )
    assert response.status_code in (200, 422)


def test_v1_streaming(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "Stream a greeting"}],
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    text = response.text
    assert "data: [DONE]" in text
    assert "chat.completion.chunk" in text


def test_v1_usage_in_response(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    data = response.json()
    assert "usage" in data
    assert "prompt_tokens" in data["usage"]
    assert "completion_tokens" in data["usage"]
    assert "total_tokens" in data["usage"]


def test_v1_native_ask_still_works(client: TestClient) -> None:
    response = client.post(
        "/ask",
        json={"provider": "fake", "prompt": "hello"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_v1_native_run_still_works(client: TestClient) -> None:
    response = client.post(
        "/run",
        json={"provider": "fake", "task": "test task", "max_steps": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data


def test_v1_tools_accepted_without_execution(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "subscription-bridge-fake",
            "messages": [{"role": "user", "content": "Use tools"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read a file",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] is not None
