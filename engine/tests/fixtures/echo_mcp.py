"""Tiny stdio MCP server for tests (mcp 2.x: FastMCP is now MCPServer)."""
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("echo")


@mcp.tool()
def price(sku: str) -> str:
    """Giá của một mã sản phẩm."""
    return f"{sku}: 189000"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "http":
        mcp.run("streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        mcp.run()
