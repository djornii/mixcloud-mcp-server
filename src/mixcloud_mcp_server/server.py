"""The MCP server: one FastMCP instance, one entry point.

stdout is the MCP JSON-RPC channel. Nothing in this package may print() to it
except the CLI flags below, which exit before the transport starts.
"""

import argparse
import json

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

from . import __version__, config
from .tools import register

SERVER_NAME = "mixcloud"

mcp = FastMCP(SERVER_NAME)
register(mcp)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config.load()
    if args.print_config:
        print(json.dumps(config.describe(), indent=2))
        return 0
    mcp.run()
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=SERVER_NAME, description="Mixcloud MCP server")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="print resolved paths and which credentials exist, then exit",
    )
    return parser.parse_args(argv)
