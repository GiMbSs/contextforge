"""Protocol tests for the read-only ContextForge MCP adapter."""

from __future__ import annotations

from pathlib import Path

import anyio
from mcp.client import Client

from contextforge.adapters.mcp import CONTEXT_TOOL_NAME, create_mcp_server


def test_mcp_legacy_handshake_lists_read_only_context_tool() -> None:
    async def scenario() -> None:
        async with Client(create_mcp_server(), mode="legacy") as client:
            result = await client.list_tools()

        assert len(result.tools) == 1
        tool = result.tools[0]
        assert tool.name == CONTEXT_TOOL_NAME
        assert tool.input_schema["required"] == ["task"]
        assert tool.output_schema is not None
        assert "project_root" in tool.input_schema["properties"]
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False

    anyio.run(scenario)


def test_mcp_tool_builds_structured_context_packet(tmp_path: Path) -> None:
    (tmp_path / "orders.py").write_text(
        "def submit_order(order_id: str) -> None:\n    validate_order(order_id)\n",
        encoding="utf-8",
    )

    async def scenario() -> None:
        async with Client(create_mcp_server(), mode="legacy") as client:
            result = await client.call_tool(
                CONTEXT_TOOL_NAME,
                {
                    "task": "Explain submit_order in orders.py",
                    "project_root": str(tmp_path),
                    "max_items": 5,
                    "max_bytes": 8192,
                },
            )

        assert result.is_error is False
        packet = result.structured_content
        assert isinstance(packet, dict)
        assert packet["packet_version"] == "contextforge-agent-context-v1"
        assert packet["budget"] == {"max_bytes": 8192, "max_items": 5}
        items = packet["items"]
        assert isinstance(items, list)
        assert items
        assert items[0]["path"] == "orders.py"
        assert "submit_order" in items[0]["content"]

    anyio.run(scenario)


def test_mcp_tool_returns_self_correctable_argument_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with Client(create_mcp_server(), mode="legacy") as client:
            result = await client.call_tool(
                CONTEXT_TOOL_NAME,
                {
                    "task": "Explain the project",
                    "project_root": str(tmp_path),
                    "max_items": 101,
                },
            )

        assert result.is_error is True
        text = " ".join(str(getattr(block, "text", "")) for block in result.content)
        assert "CF_MCP_INVALID_ARGUMENT" in text
        assert "100" in text

    anyio.run(scenario)


def test_mcp_tool_does_not_expose_mutating_operations() -> None:
    async def scenario() -> None:
        async with Client(create_mcp_server(), mode="legacy") as client:
            result = await client.list_tools()

        names: set[str] = {tool.name for tool in result.tools}
        forbidden = {"apply", "approve", "invoke", "patch", "write"}
        assert not any(part in name for name in names for part in forbidden)

    anyio.run(scenario)
