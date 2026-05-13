from __future__ import annotations

from pathlib import Path


def expand_user_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def ensure_dir(path: str | Path) -> Path:
    resolved = expand_user_path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def config_dir() -> Path:
    return project_root() / "configs"


def get_config_path(name: str) -> Path | None:
    candidate = config_dir() / name
    if candidate.exists():
        return candidate
    return None


def get_app_data_dir() -> Path:
    default = Path.home() / ".subscription-bridge"
    import os

    raw = os.environ.get("BRIDGE_DATA_DIR", str(default))
    return ensure_dir(raw)


def get_log_dir() -> Path:
    default = get_app_data_dir() / "logs"
    return ensure_dir(default)


def get_index_dir() -> Path:
    default = get_app_data_dir() / "index"
    return ensure_dir(default)


def get_debug_dir() -> Path:
    default = get_app_data_dir() / "debug"
    return ensure_dir(default)
