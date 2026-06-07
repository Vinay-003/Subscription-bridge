from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkspaceResolution:
    path: str
    source: str


def normalize_workspace(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    try:
        resolved = os.path.expanduser(value)
        resolved = os.path.abspath(resolved)
    except Exception:
        return None
    if os.path.isdir(resolved):
        return resolved
    return None


def workspace_from_messages(messages: list[Any]) -> str | None:
    patterns = [
        r"workspace\s*[:=]\s*`?(/[^\s`]+)`?",
        r"project\s*(?:root|dir|directory)?\s*[:=]\s*`?(/[^\s`]+)`?",
        r"working\s*directory\s*[:=]\s*`?(/[^\s`]+)`?",
        r"cwd\s*[:=]\s*`?(/[^\s`]+)`?",
    ]
    for msg in messages:
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            continue
        for pat in patterns:
            match = re.search(pat, content, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().rstrip(".,;:>)\"]}'")
                normalized = normalize_workspace(candidate)
                if normalized:
                    return normalized
    return None


def workspace_from_opencode_db(model_id: str | None = None) -> str | None:
    data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    db_path = os.environ.get("OPENCODE_DB_PATH", os.path.join(data_home, "opencode", "opencode.db"))
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=0.2)
    except Exception:
        return None
    try:
        cursor = conn.cursor()
        if model_id:
            cursor.execute(
                "select m.data, s.directory from message m "
                "join session s on s.id = m.session_id "
                "where m.data like ? "
                "and m.data like ? "
                "and s.directory is not null and s.directory != '' "
                "and (s.time_archived is null or s.time_archived = 0) "
                "order by m.time_updated desc limit 50",
                (
                    '%"providerID":"subscription-bridge"%',
                    f'%"modelID":"{_strip_provider_prefix(model_id)}"%',
                ),
            )
            rows = cursor.fetchall()
            for row in rows:
                if not row:
                    continue
                msg_data = row[0] if len(row) > 0 else None
                session_dir = row[1] if len(row) > 1 else None
                try:
                    parsed = json.loads(msg_data) if isinstance(msg_data, str) else {}
                except Exception:
                    parsed = {}
                if isinstance(parsed, dict):
                    path_obj = parsed.get("path")
                    if isinstance(path_obj, dict):
                        cwd = path_obj.get("cwd")
                        normalized = normalize_workspace(str(cwd) if cwd else None)
                        if normalized:
                            return normalized
                normalized_session_dir = normalize_workspace(str(session_dir) if session_dir else None)
                if normalized_session_dir:
                    return normalized_session_dir

        cursor.execute(
            "select s.directory from session s "
            "where s.directory is not null and s.directory != '' "
            "and (s.time_archived is null or s.time_archived = 0) "
            "order by s.time_updated desc limit 1"
        )
        row = cursor.fetchone()
        if row and row[0]:
            normalized = normalize_workspace(str(row[0]))
            if normalized:
                return normalized
        cursor.execute(
            "select worktree from project where worktree is not null "
            "and worktree != '' order by time_updated desc limit 1"
        )
        row = cursor.fetchone()
        if row and row[0]:
            normalized = normalize_workspace(str(row[0]))
            if normalized:
                return normalized
        return None
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def resolve_workspace(req: Any, request: Any) -> WorkspaceResolution:
    headers = [
        ("x-workspace-root", request.headers.get("x-workspace-root")),
        ("x-workspace", request.headers.get("x-workspace")),
        ("x-opencode-workspace", request.headers.get("x-opencode-workspace")),
        ("x-opencode-project", request.headers.get("x-opencode-project")),
    ]
    for name, raw in headers:
        normalized = normalize_workspace(raw)
        if normalized:
            return WorkspaceResolution(normalized, name)

    normalized = normalize_workspace(getattr(req, "workspace", None))
    if normalized:
        return WorkspaceResolution(normalized, "body")

    messages = getattr(req, "messages", [])
    from_messages = workspace_from_messages(messages)
    if from_messages:
        return WorkspaceResolution(from_messages, "messages")

    if os.environ.get("SUBSCRIPTION_BRIDGE_OPENCODE_DB_PROBE", "0").lower() in {"1", "true", "yes"}:
        from_opencode = workspace_from_opencode_db(getattr(req, "model", None))
        if from_opencode:
            return WorkspaceResolution(from_opencode, "opencode_db")

    return WorkspaceResolution(os.path.abspath("."), "default")


def _strip_provider_prefix(model_id: str) -> str:
    if "/" in model_id:
        return model_id.split("/", 1)[1]
    return model_id
