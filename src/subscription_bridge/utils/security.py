from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?\S+['\"]?"),
    re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?\S+['\"]?"),
    re.compile(r"(?i)(access[_-]?token|accesstoken)\s*[:=]\s*['\"]?\S+['\"]?"),
    re.compile(r"(?i)(secret|secret_key)\s*[:=]\s*['\"]?\S+['\"]?"),
    re.compile(r"(?i)(auth[_-]?token|authtoken)\s*[:=]\s*['\"]?\S+['\"]?"),
    re.compile(r"(?i)(bearer|bearer_token)\s*\S+"),
    re.compile(r"(?i)(session[_-]?id|sessionid)\s*[:=]\s*['\"]?\S+['\"]?"),
    re.compile(r"(?i)(refresh[_-]?token)\s*[:=]\s*['\"]?\S+['\"]?"),
]

_CREDENTIALS_IN_URL = re.compile(r"(://)([^:]+):([^@]+)@")


def redact_secret(value: str) -> str:
    if not value:
        return value
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=<REDACTED>", value)
    return value


def redact_url_credentials(url: str) -> str:
    if not url:
        return url
    return _CREDENTIALS_IN_URL.sub(r"\1<USER>:<PASS>@", url)


def sanitize_for_log(data: Any, max_depth: int = 5) -> Any:
    if max_depth <= 0:
        return "<max depth>"

    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                result[key] = "<REDACTED>"
            else:
                result[key] = sanitize_for_log(value, max_depth - 1)
        return result

    if isinstance(data, (list, tuple)):
        return [sanitize_for_log(item, max_depth - 1) for item in data]

    if isinstance(data, str):
        data = redact_url_credentials(data)
        data = redact_secret(data)
        return data

    return data


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    sensitive_terms = {
        "password", "passwd", "secret", "token", "api_key", "apikey",
        "access_token", "auth_token", "session_id", "sessionid",
        "refresh_token", "private_key", "cookie", "cookies",
        "authorization", "credentials", "jwt",
    }
    return lower in sensitive_terms or any(
        term in lower for term in sensitive_terms
    )
