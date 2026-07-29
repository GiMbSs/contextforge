"""Model Context Protocol adapter for external coding agents."""

from contextforge.adapters.mcp.server import (
    CONTEXT_TOOL_NAME,
    create_mcp_server,
    serve_mcp,
)

__all__ = ["CONTEXT_TOOL_NAME", "create_mcp_server", "serve_mcp"]
