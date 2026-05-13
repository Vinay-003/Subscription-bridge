from __future__ import annotations

from pathlib import Path

from subscription_bridge.utils.paths import (
    config_dir,
    ensure_dir,
    expand_user_path,
    get_config_path,
    project_root,
)


def test_expand_user_path() -> None:
    path = expand_user_path("~")
    assert path == Path.home().resolve()


def test_expand_user_path_relative() -> None:
    path = expand_user_path(".")
    assert path.is_absolute()


def test_ensure_dir_creates(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir"
    assert not target.exists()
    result = ensure_dir(target)
    assert result == target.resolve()
    assert target.exists()
    assert target.is_dir()


def test_ensure_dir_existing(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    result = ensure_dir(target)
    assert result == target.resolve()
    assert target.exists()


def test_project_root() -> None:
    root = project_root()
    assert (root / "pyproject.toml").exists()


def test_config_dir() -> None:
    cfg_dir = config_dir()
    assert (cfg_dir / "app.yaml").exists()


def test_get_config_path_found() -> None:
    path = get_config_path("app.yaml")
    assert path is not None
    assert path.exists()


def test_get_config_path_not_found() -> None:
    path = get_config_path("nonexistent.yaml")
    assert path is None
