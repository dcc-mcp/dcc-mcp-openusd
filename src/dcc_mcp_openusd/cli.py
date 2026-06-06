"""Command-line entry point for dcc-mcp-openusd.

Supports foreground, daemon, and ``uvx dcc-mcp-openusd`` one-shot launch.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from typing import Optional

from dcc_mcp_openusd.__version__ import __version__
from dcc_mcp_openusd.server import DEFAULT_PORT, OpenUsdMcpServer, start_server, stop_server

logger = logging.getLogger(__name__)


def main(argv: Optional[list[str]] = None) -> int:
    """Run the OpenUSD MCP server (foreground or daemon)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.debug)

    if args.version:
        print(f"dcc-mcp-openusd {__version__}")
        return 0

    # ── daemon mode ────────────────────────────────────────────────────
    if args.daemon:
        return _run_daemon(args)

    # ── foreground mode ────────────────────────────────────────────────
    server = _build_server(args)
    server.start()

    print(f"OpenUSD MCP server started: {server.mcp_url}")
    if server.gateway_url:
        print(f"Gateway URL: {server.gateway_url}")
    print("Press Ctrl+C to stop...")

    _install_signal_handlers()

    try:
        _wait_for_shutdown(server)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        stop_server()
    return 0


# ── CLI parser ────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dcc-mcp-openusd",
        description="OpenUSD MCP Server — headless daemon for Pixar USD scene authoring over MCP",
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # Server networking
    net = parser.add_argument_group("networking")
    net.add_argument("--port", type=int, default=None, help=f"Port to listen on (default: {DEFAULT_PORT})")
    net.add_argument("--gateway-port", type=int, default=None, help="Gateway port for multi-instance failover")
    net.add_argument("--registry-dir", default=None, help="Optional gateway registry directory")

    # OpenUSD context
    usd = parser.add_argument_group("openusd")
    usd.add_argument("--project-dir", default=None, help="Active OpenUSD project directory")

    # Gateway / failover
    gw = parser.add_argument_group("gateway")
    gw.add_argument(
        "--enable-gateway-failover",
        action="store_true",
        default=None,
        help="Enable automatic gateway failover election",
    )
    gw.add_argument(
        "--no-gateway-failover",
        action="store_false",
        dest="enable_gateway_failover",
        help="Disable gateway failover",
    )

    # Observability
    obs = parser.add_argument_group("observability")
    obs.add_argument("--metrics", action="store_true", help="Enable Prometheus metrics when supported by core")
    obs.add_argument("--no-file-logging", action="store_true", help="Disable rolling file logging")

    # Daemon
    dmn = parser.add_argument_group("daemon")
    dmn.add_argument("--daemon", action="store_true", help="Detach and run as a background daemon")
    dmn.add_argument("--pidfile", default=None, help="Write daemon PID to this file (default: auto-generated)")

    # Extra skills
    parser.add_argument(
        "--extra-skill-path",
        action="append",
        default=None,
        dest="extra_skill_paths",
        help="Additional skill directory (repeatable)",
    )

    return parser


# ── helpers ────────────────────────────────────────────────────────────────


def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _build_server(args: argparse.Namespace) -> OpenUsdMcpServer:
    """Construct an OpenUsdMcpServer from parsed CLI args + env.

    ``--port 0`` is preserved so core can let the OS assign a free port.
    """
    port = args.port
    if port is None:
        env_port = os.environ.get("DCC_MCP_OPENUSD_PORT")
        port = int(env_port) if env_port else DEFAULT_PORT

    # Gateway failover: CLI flag wins, then env var, then server default
    enable_gateway_failover = args.enable_gateway_failover
    if enable_gateway_failover is None:
        env_val = os.environ.get("DCC_MCP_OPENUSD_GATEWAY_FAILOVER", "").strip().lower()
        if env_val in ("1", "true", "yes"):
            enable_gateway_failover = True
        elif env_val in ("0", "false", "no"):
            enable_gateway_failover = False

    gateway_port = args.gateway_port
    if gateway_port is None:
        env_gw = os.environ.get("DCC_MCP_OPENUSD_GATEWAY_PORT")
        if env_gw:
            gateway_port = int(env_gw)

    registry_dir = args.registry_dir or os.environ.get("DCC_MCP_REGISTRY_DIR")

    return start_server(
        port=port,
        extra_skill_paths=args.extra_skill_paths,
        gateway_port=gateway_port,
        registry_dir=registry_dir,
        project_dir=args.project_dir,
        enable_gateway_failover=enable_gateway_failover,
        enable_file_logging=not args.no_file_logging,
        metrics_enabled=args.metrics,
    )


def _run_daemon(args: argparse.Namespace) -> int:
    """Daemonise the OpenUSD MCP server process."""
    pidfile = args.pidfile
    if not pidfile:
        import tempfile

        pidfile = os.path.join(tempfile.gettempdir(), "dcc-mcp-openusd.pid")

    try:
        from dcc_mcp_core.daemon_launch import Daemon

        daemon = Daemon(pidfile=pidfile)
        logger.info("Daemonizing dcc-mcp-openusd (pidfile=%s)", pidfile)
        daemon.daemonize()

        # Now running as the detached daemon child.
        server = _build_server(args)
        server.start()

        logger.info(
            "[openusd] Daemon listening on %s (pid=%d)",
            server.mcp_url,
            daemon.pid,
        )

        # Run forever; the daemon owns its lifecycle.
        _install_signal_handlers()
        _wait_for_shutdown(server)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logger.error("Daemon failed: %s", exc, exc_info=True)
        return 1
    finally:
        stop_server()
    return 0


# ── signal handling ───────────────────────────────────────────────────────


_signal_received: bool = False


def _handle_signal(signum: int, _frame: object) -> None:
    """Set the shutdown flag and tear down the server immediately.

    Does **not** call ``sys.exit`` — the main loop polls ``_signal_received``
    and exits cleanly through ``stop_server()`` in the ``finally`` block.
    The inline ``stop_server()`` here shortens the window before the next
    ``time.sleep(1)`` poll iteration.
    """
    global _signal_received
    _signal_received = True
    logger.info("Received signal %d, shutting down...", signum)
    try:
        stop_server()
    except Exception:
        pass


def _wait_for_shutdown(server: OpenUsdMcpServer) -> None:
    while server.is_running and not _signal_received:
        time.sleep(1)


def _install_signal_handlers() -> None:
    global _signal_received
    _signal_received = False
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass  # Not available on this platform or thread


if __name__ == "__main__":
    sys.exit(main())
