from __future__ import annotations

from subscription_bridge.tools.file_write import FileWriteTool


def test_file_write_guidance_does_not_prefer_bash_heredocs() -> None:
    description = FileWriteTool.description

    assert "prefer the patch tool" in description
    assert "heredoc" not in description.lower()
