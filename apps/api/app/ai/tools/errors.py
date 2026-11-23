from typing import Literal

ToolErrorCode = Literal[
    "invalid_arguments",
    "not_found",
    "unavailable",
    "timeout",
    "limit_exceeded",
    "forbidden",
]


class ToolError(Exception):
    """Structured error for tool execution failure.

    Guarantees:
    - Never leaks SQL queries, internal stack traces, or other users' data.
    - Provides a safe user-facing message and machine-readable code.
    """

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
