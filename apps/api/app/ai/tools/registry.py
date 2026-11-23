import json
from typing import Any

from app.ai.tools.base import Tool
from app.ai.tools.errors import ToolError


class SchemaSecurityViolationError(Exception):
    """Raised when an exported LLM tool schema contains prohibited identifiers."""
    pass


PROHIBITED_SCHEMA_FIELDS = {
    "user_id",
    "account_id",
    "owner_id",
    "owner",
    "sql",
    "raw_sql",
    "query_string",
}


def assert_schema_is_secure(schema_dict: dict[str, Any]) -> None:
    """Security audit asserting that an exported tool schema contains no user identity or SQL injection vectors."""
    # Convert entire schema to JSON string to check all keys and property descriptions
    serialized = json.dumps(schema_dict).lower()
    for field_name in PROHIBITED_SCHEMA_FIELDS:
        # Check if the field is present as a JSON key or property name
        if f'"{field_name}"' in serialized:
            raise SchemaSecurityViolationError(
                f"Security Violation: LLM-visible schema exposes prohibited field '{field_name}'"
            )


class ToolRegistry:
    """Central registry for discovering, retrieving, and exporting LLM-visible tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError("not_found", f"Tool '{name}' is not recognized")
        return self._tools[name]

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def export_schemas(self) -> list[dict[str, Any]]:
        """Export OpenAI/Gemini-compatible tool declarations with strict security validation."""
        exported: list[dict[str, Any]] = []
        for tool in self._tools.values():
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_model.model_json_schema(),
                },
            }
            # Enforce hard security guarantee
            assert_schema_is_secure(schema)
            exported.append(schema)
        return exported


default_registry = ToolRegistry()
