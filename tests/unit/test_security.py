from __future__ import annotations

from subscription_bridge.utils.security import (
    redact_secret,
    redact_url_credentials,
    sanitize_for_log,
)


def test_redact_secret_password() -> None:
    result = redact_secret("password=supersecret123")
    assert "<REDACTED>" in result
    assert "supersecret123" not in result


def test_redact_secret_api_key() -> None:
    result = redact_secret("api_key: abcdef12345")
    assert "<REDACTED>" in result
    assert "abcdef12345" not in result


def test_redact_secret_access_token() -> None:
    result = redact_secret("access_token=eyJhbGciOiJIUzI1NiJ9")
    assert "<REDACTED>" in result
    assert "eyJhbGciOiJIUzI1NiJ9" not in result


def test_redact_secret_empty() -> None:
    assert redact_secret("") == ""


def test_redact_secret_noop() -> None:
    result = redact_secret("hello world this is safe")
    assert result == "hello world this is safe"


def test_redact_url_credentials() -> None:
    result = redact_url_credentials("http://user:pass@example.com/data")
    assert "<USER>:<PASS>" in result
    assert "user:pass" not in result


def test_redact_url_credentials_no_creds() -> None:
    url = "https://example.com/data"
    result = redact_url_credentials(url)
    assert result == url


def test_redact_url_credentials_empty() -> None:
    assert redact_url_credentials("") == ""


def test_sanitize_for_log_dict_with_sensitive() -> None:
    data = {
        "username": "alice",
        "password": "hunter2",
        "api_key": "sk-abc123",
        "message": "hello",
    }
    result = sanitize_for_log(data)
    assert result["username"] == "alice"
    assert result["password"] == "<REDACTED>"
    assert result["api_key"] == "<REDACTED>"
    assert result["message"] == "hello"


def test_sanitize_for_log_nested_dict() -> None:
    data = {"user": {"email": "a@b.com", "token": "abc123"}, "safe": "ok"}
    result = sanitize_for_log(data)
    assert result["user"]["token"] == "<REDACTED>"
    assert result["user"]["email"] == "a@b.com"
    assert result["safe"] == "ok"


def test_sanitize_for_log_list() -> None:
    data = [{"password": "secret"}, "hello"]
    result = sanitize_for_log(data)
    assert result[0]["password"] == "<REDACTED>"
    assert result[1] == "hello"


def test_sanitize_for_log_redacts_in_string_values() -> None:
    data = {"url": "http://user:pass@example.com", "config": "password=secret123"}
    result = sanitize_for_log(data)
    assert "user:pass" not in result["url"]
    assert "<USER>:<PASS>" in result["url"]
    assert "secret123" not in result["config"]
    assert "<REDACTED>" in result["config"]


def test_sanitize_for_log_max_depth() -> None:
    deeply_nested: dict = {}
    current = deeply_nested
    for _ in range(10):
        current["next"] = {}
        current = current["next"]

    result = sanitize_for_log(deeply_nested, max_depth=3)
    assert result["next"]["next"]["next"] == "<max depth>"


def test_sanitize_for_log_non_dict_types() -> None:
    assert sanitize_for_log(42) == 42
    assert sanitize_for_log(None) is None
    assert sanitize_for_log(True) is True
