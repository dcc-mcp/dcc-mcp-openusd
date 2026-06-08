"""Headless OpenUSD MCP server wiring with daemon runtime integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core import DccServerOptions
from dcc_mcp_core.server_base import DccServerBase

from dcc_mcp_openusd.__version__ import __version__

logger = logging.getLogger(__name__)

SERVER_NAME = "dcc-mcp-openusd"
SERVER_VERSION = __version__
DEFAULT_PORT = 8765

_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
_DCC_NAME = "openusd"


@dataclass
class OpenUsdServerOptions:
    """Adapter-local options collapsed into the dcc-mcp-core server contract."""

    port: int = DEFAULT_PORT
    extra_skill_paths: Optional[List[str]] = None
    server_name: str = SERVER_NAME
    server_version: str = SERVER_VERSION
    gateway_port: Optional[int] = None
    registry_dir: Optional[str] = None
    project_dir: Optional[str] = None
    enable_gateway_failover: Optional[bool] = None
    enable_file_logging: bool = True
    enable_job_persistence: bool = True
    enable_telemetry: bool = True
    metrics_enabled: Optional[bool] = None
    dcc_pid: Optional[int] = None

    def to_core_options(self) -> DccServerOptions:
        """Convert this adapter config to ``DccServerOptions``."""
        return DccServerOptions.from_env(
            dcc_name=_DCC_NAME,
            builtin_skills_dir=_BUILTIN_SKILLS_DIR,
            port=self.port,
            server_name=self.server_name,
            server_version=self.server_version,
            gateway_port=self.gateway_port,
            registry_dir=self.registry_dir,
            dcc_version="OpenUSD",
            scene=self.project_dir,
            enable_gateway_failover=self.enable_gateway_failover,
            enable_file_logging=self.enable_file_logging,
            enable_job_persistence=self.enable_job_persistence,
            enable_telemetry=self.enable_telemetry,
            dcc_pid=self.dcc_pid,
            standalone_main_thread=True,
        )


class OpenUsdMcpServer(DccServerBase):
    """Headless MCP server for OpenUSD project and stage skills.

    Wraps :class:`DccServerBase` with OpenUSD-specific defaults and
    runtime detection. Supports daemon mode, gateway failover, and
    diagnostic tools out of the box.
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        extra_skill_paths: Optional[List[str]] = None,
        server_name: str = SERVER_NAME,
        server_version: str = SERVER_VERSION,
        gateway_port: Optional[int] = None,
        registry_dir: Optional[str] = None,
        project_dir: Optional[str] = None,
        enable_gateway_failover: Optional[bool] = None,
        enable_file_logging: bool = True,
        enable_job_persistence: bool = True,
        enable_telemetry: bool = True,
        metrics_enabled: Optional[bool] = None,
        options: Optional[OpenUsdServerOptions] = None,
    ) -> None:
        if options is None:
            options = OpenUsdServerOptions(
                port=port,
                extra_skill_paths=extra_skill_paths,
                server_name=server_name,
                server_version=server_version,
                gateway_port=gateway_port,
                registry_dir=registry_dir,
                project_dir=project_dir,
                enable_gateway_failover=enable_gateway_failover,
                enable_file_logging=enable_file_logging,
                enable_job_persistence=enable_job_persistence,
                enable_telemetry=enable_telemetry,
                metrics_enabled=metrics_enabled,
            )

        super().__init__(options=options.to_core_options())
        self._extra_skill_paths: List[str] = list(options.extra_skill_paths or [])
        if options.metrics_enabled:
            self._config.enable_prometheus = True

    @property
    def port(self) -> int:
        """Return the active TCP port."""
        if self._handle is not None:
            try:
                return int(self._handle.port)
            except Exception:
                pass
        return int(self._options.port)

    @property
    def mcp_url(self) -> str:
        """Return the Streamable HTTP MCP endpoint URL."""
        return f"http://127.0.0.1:{self.port}/mcp"

    @property
    def gateway_url(self) -> Optional[str]:
        """Return the gateway endpoint URL when this instance is the active gateway."""
        try:
            gw_port = getattr(self._config, "gateway_port", 0)
            if gw_port > 0 and self.is_gateway:
                return f"http://127.0.0.1:{gw_port}/mcp"
        except Exception:
            pass
        return None

    @property
    def daemon_status(self) -> Dict[str, Any]:
        """Return the gateway daemon health status dict."""
        return dict(getattr(self, "_gateway_daemon_status", {}) or {})

    @property
    def gateway_runtime_mode(self) -> str:
        """Return the current gateway runtime mode label."""
        return str(getattr(self, "_gateway_runtime_mode", "unknown") or "unknown")

    def _version_string(self) -> str:
        """Return a compact OpenUSD runtime label."""
        try:
            from pxr import Usd  # type: ignore

            version = getattr(Usd, "GetVersion", lambda: None)()
            if version:
                return "OpenUSD " + ".".join(str(part) for part in version)
        except Exception:
            pass
        return "OpenUSD (pxr detection fallback)"

    def register_builtin_actions(
        self,
        extra_skill_paths: Optional[List[str]] = None,
        include_bundled: bool = True,
        minimal_mode: Any = None,
    ) -> None:
        """Discover bundled OpenUSD skills."""
        paths = list(extra_skill_paths or [])
        paths.extend(self._extra_skill_paths)
        super().register_builtin_actions(
            extra_skill_paths=paths or None,
            include_bundled=include_bundled,
            minimal_mode=minimal_mode,
        )

    def start(self, *, install_atexit_hook: bool = True) -> "OpenUsdMcpServer":
        """Start the MCP HTTP server and return ``self``."""
        super().start(install_atexit_hook=install_atexit_hook)
        return self

    def list_skills(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List discovered skills."""
        if self._handle is None:
            return []
        return list(self._server.list_skills(status=status))


_server_instance: Optional[OpenUsdMcpServer] = None


def start_server(
    port: int = DEFAULT_PORT,
    extra_skill_paths: Optional[List[str]] = None,
    register_builtins: bool = True,
    include_bundled: bool = True,
    gateway_port: Optional[int] = None,
    registry_dir: Optional[str] = None,
    project_dir: Optional[str] = None,
    enable_gateway_failover: Optional[bool] = None,
    enable_file_logging: bool = True,
    enable_job_persistence: bool = True,
    enable_telemetry: bool = True,
    metrics_enabled: Optional[bool] = None,
) -> OpenUsdMcpServer:
    """Start the process-level OpenUSD MCP server singleton."""
    global _server_instance  # noqa: PLW0603

    if _server_instance is not None and _server_instance.is_running:
        return _server_instance

    _server_instance = OpenUsdMcpServer(
        port=port,
        extra_skill_paths=extra_skill_paths,
        gateway_port=gateway_port,
        registry_dir=registry_dir,
        project_dir=project_dir,
        enable_gateway_failover=enable_gateway_failover,
        enable_file_logging=enable_file_logging,
        enable_job_persistence=enable_job_persistence,
        enable_telemetry=enable_telemetry,
        metrics_enabled=metrics_enabled,
    )
    if register_builtins:
        _server_instance.register_builtin_actions(include_bundled=include_bundled)
    _server_instance.start()
    logger.info("[%s] MCP server listening on %s", _DCC_NAME, _server_instance.mcp_url)
    return _server_instance


def stop_server() -> None:
    """Stop the running server, if any."""
    global _server_instance  # noqa: PLW0603
    if _server_instance is None:
        return
    _server_instance.stop()
    _server_instance = None


def get_server() -> Optional[OpenUsdMcpServer]:
    """Return the current server singleton."""
    return _server_instance
