"""Tests for the dcc-mcp-openusd CLI and daemon integration."""

from __future__ import annotations

import signal
from unittest import mock

from dcc_mcp_openusd.cli import _build_parser, _build_server, _handle_signal, main
from dcc_mcp_openusd.server import DEFAULT_PORT

# ── parser / flag existence ────────────────────────────────────────────────


def test_cli_parser_has_daemon_flags():
    """Ensure the CLI parser exposes all daemon-related flags."""
    parser = _build_parser()
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
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_uvx_discoverable():
    """dcc-mcp-openusd must be discoverable by uvx."""
    import sys

    if sys.version_info >= (3, 12):
        from importlib.metadata import entry_points

        eps = entry_points(group="console_scripts")
    elif sys.version_info >= (3, 10):
        from importlib.metadata import entry_points

        eps = entry_points().get("console_scripts", [])  # type: ignore[attr-defined]
    else:
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


# ── behavioral: port 0 semantics ───────────────────────────────────────────


def test_port_zero_is_preserved():
    """--port 0 must be passed through as 0, NOT fall back to DEFAULT_PORT."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--port", "0"])
        _build_server(args)
        mock_start.assert_called_once()
        _, kwargs = mock_start.call_args
        assert kwargs["port"] == 0, f"expected port=0, got {kwargs['port']}"


def test_port_absent_uses_default():
    """When --port is not given, DEFAULT_PORT is used."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args([])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["port"] == DEFAULT_PORT


# ── behavioral: parameter forwarding ───────────────────────────────────────


def test_enable_gateway_failover_is_wired():
    """--enable-gateway-failover must reach start_server."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--enable-gateway-failover"])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["enable_gateway_failover"] is True


def test_no_gateway_failover_is_wired():
    """--no-gateway-failover must reach start_server."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--no-gateway-failover"])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["enable_gateway_failover"] is False


def test_no_file_logging_is_wired():
    """--no-file-logging must flip enable_file_logging to False."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--no-file-logging"])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["enable_file_logging"] is False


def test_no_file_logging_defaults_true():
    """By default (no --no-file-logging), enable_file_logging is True."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args([])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["enable_file_logging"] is True


def test_project_dir_is_wired():
    """--project-dir must reach start_server."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--project-dir", "/tmp/myproj"])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["project_dir"] == "/tmp/myproj"


def test_extra_skill_paths_is_wired():
    """--extra-skill-path (repeatable) must be aggregated."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--extra-skill-path", "/a", "--extra-skill-path", "/b"])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["extra_skill_paths"] == ["/a", "/b"]


def test_metrics_is_wired():
    """--metrics must reach start_server."""
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--metrics"])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["metrics_enabled"] is True


# ── behavioral: CLI vs env priority ────────────────────────────────────────


def test_cli_port_beats_env(monkeypatch):
    """CLI --port must take priority over DCC_MCP_OPENUSD_PORT env var."""
    monkeypatch.setenv("DCC_MCP_OPENUSD_PORT", "9999")
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--port", "5000"])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["port"] == 5000, "CLI --port should override env"


def test_env_port_fallback(monkeypatch):
    """When --port is absent, DCC_MCP_OPENUSD_PORT env var is used."""
    monkeypatch.setenv("DCC_MCP_OPENUSD_PORT", "9999")
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args([])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["port"] == 9999, "env DCC_MCP_OPENUSD_PORT should be used"


def test_cli_gateway_port_beats_env(monkeypatch):
    """CLI --gateway-port must take priority over env var."""
    monkeypatch.setenv("DCC_MCP_OPENUSD_GATEWAY_PORT", "8888")
    with mock.patch("dcc_mcp_openusd.cli.start_server") as mock_start:
        args = _build_parser().parse_args(["--gateway-port", "7777"])
        _build_server(args)
        _, kwargs = mock_start.call_args
        assert kwargs["gateway_port"] == 7777


# ── behavioral: signal handling ────────────────────────────────────────────


def test_signal_handler_sets_flag():
    """_handle_signal must set _signal_received = True."""
    import dcc_mcp_openusd.cli as cli_mod

    cli_mod._signal_received = False  # reset module-level state

    try:
        _handle_signal(signal.SIGTERM, None)
        assert cli_mod._signal_received is True
    finally:
        cli_mod._signal_received = False  # restore


def test_signal_handler_calls_stop_server():
    """_handle_signal must call stop_server()."""
    with mock.patch("dcc_mcp_openusd.cli.stop_server") as mock_stop:
        _handle_signal(signal.SIGTERM, None)
        mock_stop.assert_called_once()


def test_signal_handler_stop_server_failure_is_silent():
    """If stop_server raises, _handle_signal must not propagate."""
    with mock.patch("dcc_mcp_openusd.cli.stop_server", side_effect=RuntimeError("boom")):
        # Must not raise
        _handle_signal(signal.SIGTERM, None)


def test_dead_host_flag_removed():
    """--host must NOT be exposed (it was a dead parameter)."""
    parser = _build_parser()
    known = {action.dest for action in parser._actions}
    assert "host" not in known, "--host was a dead flag and should be removed"
