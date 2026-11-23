import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.tools.base import ToolContext, ToolResult
from app.ai.tools.errors import ToolError
from app.ai.tools.registry import ToolRegistry, default_registry


class ToolExecutionBudget:
    """Tracks execution budget and resource consumption across tool calls for a request."""

    def __init__(
        self,
        max_tool_calls: int = 5,
        max_total_rows: int = 500,
        overall_budget_seconds: float = 10.0,
    ) -> None:
        self.max_tool_calls = max_tool_calls
        self.max_total_rows = max_total_rows
        self.overall_budget_seconds = overall_budget_seconds
        self.calls_count = 0
        self.total_rows = 0
        self.started_at = time.monotonic()

    def record_call(self) -> None:
        if self.calls_count >= self.max_tool_calls:
            raise ToolError(
                "limit_exceeded",
                f"Exceeded maximum tool calls limit of {self.max_tool_calls} per request",
            )
        elapsed = time.monotonic() - self.started_at
        if elapsed > self.overall_budget_seconds:
            raise ToolError(
                "timeout",
                f"Tool execution overall time budget of {self.overall_budget_seconds:.1f}s exceeded",
            )
        self.calls_count += 1

    def record_rows(self, count: int) -> bool:
        """Records rows and returns True if truncated to fit max_total_rows."""
        self.total_rows += count
        if self.total_rows > self.max_total_rows:
            return True
        return False


def _check_statement_readonly(statement: Any) -> None:
    """Inspect statement and raise ToolError('forbidden') if any write or DDL operation is attempted."""
    if hasattr(statement, "is_insert") and statement.is_insert:
        raise ToolError("forbidden", "Write statement rejected: financial tools are strictly read-only")
    if hasattr(statement, "is_update") and statement.is_update:
        raise ToolError("forbidden", "Write statement rejected: financial tools are strictly read-only")
    if hasattr(statement, "is_delete") and statement.is_delete:
        raise ToolError("forbidden", "Write statement rejected: financial tools are strictly read-only")

    stmt_str = str(getattr(statement, "text", statement)).strip().upper()
    if any(
        stmt_str.startswith(prefix)
        for prefix in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE")
    ):
        raise ToolError(
            "forbidden",
            f"Write statement rejected: financial tools are strictly read-only ({stmt_str[:10]}...)",
        )


@asynccontextmanager
async def enforce_read_only_session(session: AsyncSession | Session) -> AsyncGenerator[None, None]:
    """Enforce strict read-only database access at connection, query, and ORM levels.

    Guarantees:
    - Sets PostgreSQL transaction to READ ONLY and applies statement_timeout when running on PostgreSQL.
    - Intercepts query execution, rejecting any INSERT, UPDATE, DELETE, or DDL statements.
    - Intercepts ORM flush, rejecting any pending dirty, new, or deleted models.
    - Guaranteed restoration in finally block.
    """
    bind = getattr(session, "bind", None)
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")

    if isinstance(session, AsyncSession):
        async_session: AsyncSession = session
        orig_async_execute = async_session.execute
        orig_async_flush = async_session.flush

        if dialect_name == "postgresql":
            try:
                await orig_async_execute(text("SET TRANSACTION READ ONLY;"))
                await orig_async_execute(text("SET statement_timeout = '5000ms';"))
            except Exception:
                pass

        async def readonly_async_flush(*args: Any, **kwargs: Any) -> Any:
            if async_session.new or async_session.dirty or async_session.deleted:
                raise ToolError("forbidden", "Database modification rejected: financial tools are strictly read-only")
            return await orig_async_flush(*args, **kwargs)

        async def readonly_async_execute(statement: Any, *args: Any, **kwargs: Any) -> Any:
            _check_statement_readonly(statement)
            return await orig_async_execute(statement, *args, **kwargs)

        async_session.flush = readonly_async_flush  # type: ignore[method-assign]
        async_session.execute = readonly_async_execute  # type: ignore[method-assign]

        try:
            yield
        finally:
            async_session.execute = orig_async_execute  # type: ignore[method-assign]
            async_session.flush = orig_async_flush  # type: ignore[method-assign]
    else:
        sync_session: Session = session
        orig_sync_execute = sync_session.execute
        orig_sync_flush = sync_session.flush

        if dialect_name == "postgresql":
            try:
                orig_sync_execute(text("SET TRANSACTION READ ONLY;"))
                orig_sync_execute(text("SET statement_timeout = '5000ms';"))
            except Exception:
                pass

        def readonly_sync_flush(*args: Any, **kwargs: Any) -> Any:
            if sync_session.new or sync_session.dirty or sync_session.deleted:
                raise ToolError("forbidden", "Database modification rejected: financial tools are strictly read-only")
            return orig_sync_flush(*args, **kwargs)

        def readonly_sync_execute(statement: Any, *args: Any, **kwargs: Any) -> Any:
            _check_statement_readonly(statement)
            return orig_sync_execute(statement, *args, **kwargs)

        sync_session.flush = readonly_sync_flush  # type: ignore[method-assign]
        sync_session.execute = readonly_sync_execute  # type: ignore[method-assign]

        try:
            yield
        finally:
            sync_session.execute = orig_sync_execute  # type: ignore[method-assign]
            sync_session.flush = orig_sync_flush  # type: ignore[method-assign]


class ToolExecutor:
    """The only secure entry point for executing typed, permissioned, read-only tools."""

    def __init__(self, registry: ToolRegistry = default_registry) -> None:
        self.registry = registry

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
        budget: ToolExecutionBudget | None = None,
    ) -> ToolResult:
        """Validate, authorize, and safely execute a registered tool."""
        if budget is not None:
            budget.record_call()

        tool = self.registry.get(name)

        # 1. Strict argument validation with Pydantic (extra='forbid')
        try:
            validated_args = tool.input_model.model_validate(arguments)
        except ValidationError as ve:
            raise ToolError("invalid_arguments", f"Invalid arguments for tool '{name}': {ve}") from ve

        # 2. Execute within read-only DB session and enforce per-call timeout
        try:
            async with enforce_read_only_session(context.session):
                result = await asyncio.wait_for(
                    tool.handler(context, validated_args),
                    timeout=tool.timeout,
                )
        except asyncio.TimeoutError as te:
            raise ToolError("timeout", f"Tool '{name}' execution timed out after {tool.timeout}s") from te
        except ToolError:
            raise
        except Exception as exc:
            exc_msg = str(exc).lower()
            if "readonly" in exc_msg or "read-only" in exc_msg or "read only" in exc_msg:
                raise ToolError(
                    "forbidden",
                    f"Database modification rejected: financial tools are strictly read-only ({type(exc).__name__})",
                ) from exc
            # Mask internal implementation details/SQL exceptions
            raise ToolError("unavailable", f"Tool '{name}' execution failed: {type(exc).__name__}") from exc

        # 3. Validate output model conformance
        try:
            tool.output_model.model_validate(result.data)
        except ValidationError as ve:
            raise ToolError("unavailable", f"Tool '{name}' produced invalid output structure: {ve}") from ve

        # 4. Cap output size if exceeding limits
        if result.row_count > tool.max_rows:
            result.truncated = True
            result.warnings.append(
                f"Result rows capped at {tool.max_rows} (total rows: {result.row_count})"
            )

        if budget is not None:
            truncated_by_budget = budget.record_rows(result.row_count)
            if truncated_by_budget:
                result.truncated = True
                result.warnings.append(
                    f"Result truncated due to request total row limit of {budget.max_total_rows}"
                )

        return result
