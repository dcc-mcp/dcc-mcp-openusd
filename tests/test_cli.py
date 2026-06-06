"""Tests for the dcc-mcp-openusd CLI and daemon integration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import dcc_mcp_openusd.cli as cli
from dcc_mcp_openusd.cli import _build_parser, _build_server, _run_daemon, main
from dcc_mcp_openusd.server import DEFAULT_PORT


def test_cli_parser_has_daemon_flags():
    """Ensure the CLI parser exposes all daemon-related flags."""
    parser = _build_parser()
    # Parse a minimal help invocation so we don't need to mock.
    known = {action.dest for action in parser._actions}
    assert "daemon" in known
    assert "pidfile" in known
    assert "gateway_port" in known
    assert "enable_gateway_failover" in known
    assert "metrics" in known
    assert "port" in known
    assert "project_dir" in known
    assert "extra_skill_paths" in known


def test_cli_version_exits_zero():
    """--version should print version and return 0."""
    result = main(["--version"])
    assert result == 0


def test_cli_help_exits_zero():
    """--help should exit with code 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_uvx_discoverable():
    """dcc-mcp-openusd must be discoverable by uvx."""
    # We don't actually launch uvx (it would start a long-lived server),
    # just verify the package metadata declares the script entry point.
    import sys

    if sys.version_info >= (3, 12):
        from importlib.metadata import entry_points

        eps = entry_points(group="console_scripts")
    elif sys.version_info >= (3, 10):
        from importlib.metadata import entry_points

        eps = entry_points().get("console_scripts", [])  # type: ignore[attr-defined]
    else:
        # Python 3.9: entry_points() returns dict-like without keyword args
        from importlib.metadata import entry_points

        eps = entry_points().get("console_scripts", [])  # type: ignore[attr-defined]

    script_names = {ep.name for ep in eps}
    assert "dcc-mcp-openusd" in script_names, (
        "Missing 'dcc-mcp-openusd' console_scripts entry point — uvx will not discover it"
    )


def test_default_port_is_known():
    """The default port must match the server module constant."""
    assert DEFAULT_PORT == 8765


def test_package_imports_without_pxr():
    """Package must import cleanly even without pxr at import time."""
    import dcc_mcp_openusd

    assert dcc_mcp_openusd.__version__
    assert dcc_mcp_openusd.SERVER_NAME == "dcc-mcp-openusd"


def test_cli_pidfile_flag_accepted():
    """--pidfile should be a recognized argument."""
    parser = _build_parser()
    args = parser.parse_args(["--pidfile", "/tmp/test.pid"])
    assert args.pidfile == "/tmp/test.pid"


def test_cli_daemon_flag_accepted():
    """--daemon should be a recognized flag."""
    parser = _build_parser()
    args = parser.parse_args(["--daemon"])
    assert args.daemon is True


def test_cli_parser_rejects_unsupported_host_flag():
    """Do not advertise bind-host support until the core runtime supports it."""
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--host", "0.0.0.0"])
    assert exc_info.value.code == 2


def test_build_server_passes_file_logging_flag(monkeypatch: pytest.MonkeyPatch):
    """--no-file-logging must reach start_server()."""
    captured: dict[str, object] = {}

    def fake_start_server(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(cli, "start_server", fake_start_server)

    args = _build_parser().parse_args(["--no-file-logging", "--metrics"])
    _build_server(args)

    assert captured["enable_file_logging"] is False
    assert captured["metrics_enabled"] is True


def test_main_consumes_signal_flag(monkeypatch: pytest.MonkeyPatch):
    """Foreground mode should exit when the custom signal handler flips the flag."""

    class FakeServer:
        is_running = True
        mcp_url = "http://127.0.0.1:8765/mcp"
        gateway_url = None

        def start(self) -> None:
            return None

    stop_calls: list[str] = []

    monkeypatch.setattr(cli, "_setup_logging", lambda debug: None)
    monkeypatch.setattr(cli, "_build_server", lambda args: FakeServer())
    monkeypatch.setattr(cli, "stop_server", lambda: stop_calls.append("stop"))
    monkeypatch.setattr(cli, "_install_signal_handlers", lambda: setattr(cli, "_signal_received", True))

    assert main([]) == 0
    assert stop_calls == ["stop"]


def test_run_daemon_consumes_signal_flag(monkeypatch: pytest.MonkeyPatch):
    """Daemon mode should stop when SIGINT/SIGTERM has been recorded."""

    class FakeDaemon:
        pid = 1234

        def __init__(self, pidfile: str) -> None:
            self.pidfile = pidfile

        def daemonize(self) -> None:
            return None

    class FakeServer:
        is_running = True
        mcp_url = "http://127.0.0.1:8765/mcp"

        def start(self) -> None:
            return None

    stop_calls: list[str] = []

    monkeypatch.setattr("dcc_mcp_core.daemon_launch.Daemon", FakeDaemon)
    monkeypatch.setattr(cli, "_build_server", lambda args: FakeServer())
    monkeypatch.setattr(cli, "stop_server", lambda: stop_calls.append("stop"))
    monkeypatch.setattr(cli, "_install_signal_handlers", lambda: setattr(cli, "_signal_received", True))

    assert _run_daemon(SimpleNamespace(pidfile="test.pid")) == 0
    assert stop_calls == ["stop"]
