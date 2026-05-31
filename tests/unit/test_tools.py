from __future__ import annotations

import base64
from pathlib import Path

import pytest

from subscription_bridge.core.errors import DangerousCommandError, PathTraversalError
from subscription_bridge.tools.bash import BashTool
from subscription_bridge.tools.codebase_search import CodebaseSearchTool
from subscription_bridge.tools.file_read import FileReadTool
from subscription_bridge.tools.file_write import FileWriteTool
from subscription_bridge.tools.git_diff import GitDiffTool
from subscription_bridge.tools.grep import GrepTool


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> str:
    (tmp_path / "hello.txt").write_text("hello world\nline two\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.txt").write_text("nested content")
    return str(tmp_path)


@pytest.mark.asyncio
async def test_file_read_success(tmp_workspace: str) -> None:
    tool = FileReadTool()
    result = await tool.run({"path": "hello.txt", "workspace": tmp_workspace})
    assert result.success
    assert "hello world" in result.output


@pytest.mark.asyncio
async def test_file_read_not_found(tmp_workspace: str) -> None:
    tool = FileReadTool()
    result = await tool.run({"path": "nonexistent.txt", "workspace": tmp_workspace})
    assert not result.success
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_file_read_empty_path(tmp_workspace: str) -> None:
    tool = FileReadTool()
    result = await tool.run({"path": "", "workspace": tmp_workspace})
    assert not result.success
    assert "required" in result.error


@pytest.mark.asyncio
async def test_file_read_path_traversal(tmp_workspace: str) -> None:
    tool = FileReadTool()
    with pytest.raises(PathTraversalError):
        await tool.run({"path": "../outside.txt", "workspace": tmp_workspace})


@pytest.mark.asyncio
async def test_file_write_success(tmp_workspace: str) -> None:
    tool = FileWriteTool()
    result = await tool.run({"path": "new_file.txt", "content": "fresh content", "workspace": tmp_workspace})
    assert result.success
    assert "Written" in result.output
    written = Path(tmp_workspace) / "new_file.txt"
    assert written.read_text() == "fresh content"


@pytest.mark.asyncio
async def test_file_write_creates_dirs(tmp_workspace: str) -> None:
    tool = FileWriteTool()
    result = await tool.run({"path": "a/b/c/deep.txt", "content": "deep", "workspace": tmp_workspace})
    assert result.success
    assert (Path(tmp_workspace) / "a/b/c/deep.txt").exists()


@pytest.mark.asyncio
async def test_file_write_path_traversal(tmp_workspace: str) -> None:
    tool = FileWriteTool()
    with pytest.raises(PathTraversalError):
        await tool.run({"path": "../../outside.txt", "content": "x", "workspace": tmp_workspace})


@pytest.mark.asyncio
async def test_file_write_empty_path(tmp_workspace: str) -> None:
    tool = FileWriteTool()
    result = await tool.run({"path": "", "content": "x", "workspace": tmp_workspace})
    assert not result.success
    assert "required" in result.error


@pytest.mark.asyncio
async def test_grep_finds_matches(tmp_workspace: str) -> None:
    tool = GrepTool()
    result = await tool.run({"query": "hello", "workspace": tmp_workspace})
    assert result.success
    assert "hello.txt" in result.output


@pytest.mark.asyncio
async def test_grep_no_matches(tmp_workspace: str) -> None:
    tool = GrepTool()
    result = await tool.run({"query": "zzz_nonexistent_zzz", "workspace": tmp_workspace})
    assert result.success
    assert "No matches" in result.output


@pytest.mark.asyncio
async def test_grep_empty_query(tmp_workspace: str) -> None:
    tool = GrepTool()
    result = await tool.run({"query": "", "workspace": tmp_workspace})
    assert not result.success
    assert "required" in result.error


@pytest.mark.asyncio
async def test_grep_include_pattern(tmp_workspace: str) -> None:
    tool = GrepTool()
    result = await tool.run({"query": "content", "include": "*.txt", "workspace": tmp_workspace})
    assert result.success
    assert "nested.txt" in result.output


@pytest.mark.asyncio
async def test_bash_success(tmp_workspace: str) -> None:
    tool = BashTool()
    result = await tool.run({"command": "echo hello", "workspace": tmp_workspace, "timeout": 5})
    assert result.success
    assert "hello" in result.output


@pytest.mark.asyncio
async def test_bash_timeout(tmp_workspace: str) -> None:
    tool = BashTool()
    result = await tool.run({"command": "sleep 10", "workspace": tmp_workspace, "timeout": 1})
    assert not result.success
    assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_bash_dangerous_command_rm_rf(tmp_workspace: str) -> None:
    tool = BashTool()
    with pytest.raises(DangerousCommandError, match="rm -rf /"):
        await tool.run({"command": "rm -rf /", "workspace": tmp_workspace})


@pytest.mark.asyncio
async def test_bash_dangerous_command_sudo(tmp_workspace: str) -> None:
    tool = BashTool()
    with pytest.raises(DangerousCommandError, match="sudo"):
        await tool.run({"command": "sudo rm -rf /tmp/x", "workspace": tmp_workspace})


@pytest.mark.asyncio
async def test_bash_empty_command(tmp_workspace: str) -> None:
    tool = BashTool()
    result = await tool.run({"command": "", "workspace": tmp_workspace})
    assert not result.success
    assert "required" in result.error


@pytest.mark.asyncio
async def test_git_diff_handles_no_git(tmp_path: Path) -> None:
    tool = GitDiffTool()
    result = await tool.run({"workspace": str(tmp_path)})
    assert result.success
    assert "not a git repository" in result.output.lower() or "no .git" in result.output.lower()


@pytest.mark.asyncio
async def test_codebase_search_no_index(tmp_workspace: str) -> None:
    tool = CodebaseSearchTool()
    result = await tool.run({"query": "hello", "workspace": tmp_workspace})
    assert result.success
    assert "No codebase index found" in result.output


@pytest.mark.asyncio
async def test_codebase_search_empty_query(tmp_workspace: str) -> None:
    tool = CodebaseSearchTool()
    result = await tool.run({"query": "", "workspace": tmp_workspace})
    assert not result.success
    assert "required" in result.error


@pytest.mark.asyncio
async def test_file_read_max_bytes(tmp_workspace: str) -> None:
    long_content = "x" * 5000
    (Path(tmp_workspace) / "long.txt").write_text(long_content)
    tool = FileReadTool()
    result = await tool.run({"path": "long.txt", "workspace": tmp_workspace, "max_bytes": 100})
    assert result.success
    assert len(result.output) < 200


@pytest.mark.asyncio
async def test_file_write_base64_content(tmp_workspace: str) -> None:
    tool = FileWriteTool()
    content = "#include <stdio.h>\nint main() { printf(\"hello\\n\"); return 0; }"
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    result = await tool.run({"path": "calc.c", "content_base64": encoded, "workspace": tmp_workspace})
    assert result.success
    written = Path(tmp_workspace) / "calc.c"
    assert written.read_text() == content


@pytest.mark.asyncio
async def test_file_write_base64_preferred_over_content(tmp_workspace: str) -> None:
    tool = FileWriteTool()
    actual = "written from base64"
    encoded = base64.b64encode(actual.encode("utf-8")).decode("utf-8")
    result = await tool.run({
        "path": "test.txt",
        "content": "should be ignored",
        "content_base64": encoded,
        "workspace": tmp_workspace,
    })
    assert result.success
    assert Path(tmp_workspace, "test.txt").read_text() == actual


@pytest.mark.asyncio
async def test_file_write_base64_invalid(tmp_workspace: str) -> None:
    tool = FileWriteTool()
    result = await tool.run({"path": "bad.txt", "content_base64": "not-valid-base64!!!", "workspace": tmp_workspace})
    assert not result.success
    assert "base64" in result.error.lower()


@pytest.mark.asyncio
async def test_file_write_no_content_no_base64(tmp_workspace: str) -> None:
    tool = FileWriteTool()
    result = await tool.run({"path": "empty.txt", "workspace": tmp_workspace})
    assert not result.success
    assert "required" in result.error.lower()
