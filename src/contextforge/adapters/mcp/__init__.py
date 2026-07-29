"""Model Context Protocol adapter for external coding agents."""

from contextforge.adapters.mcp.codex import (
    CodexRegistration,
    register_codex_server,
    render_shell_command,
)
from contextforge.adapters.mcp.server import (
    CONTEXT_TOOL_NAME,
    create_mcp_server,
    serve_mcp,
)

__all__ = [
    "CONTEXT_TOOL_NAME",
    "CodexRegistration",
    "create_mcp_server",
    "register_codex_server",
    "render_shell_command",
    "serve_mcp",
]
