"""Command-line entry point for dcc-mcp-openusd."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Optional

from dcc_mcp_openusd import start_server, stop_server


def main(argv: Optional[list[str]] = None) -> int:
    """Run the OpenUSD MCP server."""
    parser = argparse.ArgumentParser(description="OpenUSD MCP Server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--gateway-port", type=int, default=None, help="Gateway port")
    parser.add_argument("--registry-dir", default=None, help="Optional gateway registry directory")
    parser.add_argument("--project-dir", default=None, help="Optional active OpenUSD project directory")
    parser.add_argument("--metrics", action="store_true", help="Enable Prometheus metrics when supported by core")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    server = start_server(
        port=args.port,
        gateway_port=args.gateway_port,
        registry_dir=args.registry_dir,
        project_dir=args.project_dir,
        metrics_enabled=args.metrics,
    )

    print(f"OpenUSD MCP server started: {server.mcp_url}")
    print("Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_server()
    return 0


if __name__ == "__main__":
    sys.exit(main())
