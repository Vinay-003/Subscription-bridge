from __future__ import annotations


class AgentError(Exception):
    ...


class MaxStepsExceededError(AgentError):
    def __init__(self, max_steps: int) -> None:
        self.max_steps = max_steps
        super().__init__(f"Agent exceeded maximum of {max_steps} steps")


class ToolExecutionError(AgentError):
    def __init__(self, tool_name: str, message: str = "") -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool {tool_name!r} execution failed: {message}")


class ToolNotFoundError(AgentError):
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        allowed = ", ".join(sorted(["file_read", "file_write", "grep", "bash", "git_diff", "patch", "codebase_search"]))
        super().__init__(f"Tool {tool_name!r} not found. Available: {allowed}")


class PathTraversalError(AgentError):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path traversal blocked: {path!r} is outside the workspace")


class DangerousCommandError(AgentError):
    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__(f"Dangerous command rejected: {command!r}")


class ParserError(AgentError):
    def __init__(self, raw_text: str, reason: str = "") -> None:
        self.raw_text = raw_text
        self.reason = reason
        super().__init__(f"Parser error: {reason}")


class ProviderResponseError(AgentError):
    def __init__(self, provider: str, message: str = "") -> None:
        self.provider = provider
        super().__init__(f"Provider {provider!r} error: {message}")


class AgentStuckError(AgentError):
    """Raised when the loop detector sees the model repeating the same tool
    call without making progress."""

    def __init__(self, tool_name: str, message: str = "") -> None:
        self.tool_name = tool_name
        super().__init__(message)
