"""Thin adapter-owned doctor contract pending the shared Core #2320 surface."""

from __future__ import annotations

import os
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from typing import Any

from dcc_mcp_core import __version__ as core_version

from dcc_mcp_openusd.__version__ import __version__
from dcc_mcp_openusd.runtime import create_stage, detect_runtime, list_stage

MIN_CORE_VERSION = "0.19.45"
MIN_PXR_VERSION = "24.11"


def _distribution_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _version_at_least(value: object, minimum: str) -> bool:
    def parts(item: object) -> tuple[int, ...]:
        match = re.search(r"\d+(?:\.\d+)+", str(item or ""))
        return tuple(int(part) for part in match.group(0).split(".")) if match else ()

    current = parts(value)
    floor = parts(minimum)
    width = max(len(current), len(floor))
    return bool(current) and current + (0,) * (width - len(current)) >= floor + (0,) * (width - len(floor))


def _runtime_smoke(expected_mode: str) -> dict[str, Any]:
    with TemporaryDirectory(prefix="dcc-mcp-openusd-doctor-") as temp_dir:
        stage_path = Path(temp_dir) / "doctor.usda"
        created = create_stage(str(stage_path), name="Doctor")
        inspected = list_stage(str(stage_path))
    actual_mode = str(created.get("runtime") or "unknown")
    if actual_mode != expected_mode or inspected.get("runtime") != expected_mode:
        raise RuntimeError("detected runtime did not execute the matching stage path")
    if int(inspected.get("prim_count") or 0) < 1:
        raise RuntimeError("runtime smoke produced no readable prims")
    return {
        "performed": True,
        "result": "ready",
        "runtime": actual_mode,
        "prim_count": int(inspected["prim_count"]),
    }


def _daemon_report(config: dict[str, Any]) -> dict[str, Any]:
    pidfile = str(config.get("pidfile") or (Path(gettempdir()) / "dcc-mcp-openusd.pid"))
    daemon_entry = ["python", "-m", "dcc_mcp_openusd"] if os.name == "nt" else ["dcc-mcp-openusd"]
    return {
        "supported": True,
        "requested": bool(config.get("daemon_requested")),
        "pidfile": pidfile,
        "pidfile_present": Path(pidfile).expanduser().is_file(),
        "pid_identity_verified": False,
        "start_command": [*daemon_entry, "--daemon", "--pidfile", pidfile],
        "safe_stop": {
            "strategy": "verified_process_terminate" if os.name == "nt" else "verified_sigterm",
            "signal": None if os.name == "nt" else "SIGTERM",
            "verify_process_identity": True,
            "force": False,
            "remove_stale_pidfile_after_exit": os.name == "nt",
        },
    }


def _fail(
    report: dict[str, Any],
    *,
    exit_code: int,
    stage: str,
    reason: str,
    next_steps: list[dict[str, Any]],
) -> None:
    report.update(
        {
            "status": "error" if exit_code == 40 else "not_ready",
            "exit_code": exit_code,
            "directly_usable": False,
            "failure": {"stage": stage, "reason": reason},
            "next_steps": next_steps,
        }
    )


def evaluate(operation: str, config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the installed runtime without starting the standalone service."""
    detected = detect_runtime()
    mode = "pxr" if detected.has_pxr else "text-fallback"
    distribution_version = _distribution_version("usd-core") if detected.has_pxr else None
    full_capabilities = detected.has_pxr and _version_at_least(distribution_version, MIN_PXR_VERSION)
    capabilities = {
        "text_usda_authoring": True,
        "stage_inspection": True,
        "references": True,
        "native_pxr": full_capabilities,
        "material_binding": full_capabilities,
        "camera_and_lights": full_capabilities,
        "time_sampled_animation": full_capabilities,
        "layer_composition": full_capabilities,
    }
    report = {
        "schema_version": "1.0",
        "operation": operation,
        "status": "ok",
        "exit_code": 0,
        "directly_usable": True,
        "adapter": {
            "name": "dcc-mcp-openusd",
            "version": __version__,
            "runtime_shape": "standalone",
            "contract": "adapter_compatibility_pending_core_2320",
        },
        "requirements": {
            "core_version": core_version,
            "min_core_version": MIN_CORE_VERSION,
            "min_pxr_version": MIN_PXR_VERSION,
            "pxr_required_for_full_capabilities": True,
        },
        "runtime": {
            "mode": mode,
            "api_version": detected.version,
            "distribution": "usd-core" if detected.has_pxr else None,
            "distribution_version": distribution_version,
            "full_capabilities": full_capabilities,
            "verification": {"performed": False, "result": "not_requested"},
        },
        "capabilities": capabilities,
        "configuration": config,
        "endpoint": {
            "kind": "standalone_loopback_mcp",
            "requires_external_endpoint": False,
            "server_started_by_doctor": False,
            "authentication_required": False,
            "discovery_command": ["dcc-mcp-cli", "list"],
            "port": config.get("port"),
            "gateway_port": config.get("gateway_port"),
        },
        "daemon": _daemon_report(config),
        "provisioning": {
            "auto_provision": False,
            "external_payload": None,
            "persistent_adapter_cache": None,
        },
        "failure": None,
        "next_steps": [],
        "optional_next_steps": []
        if detected.has_pxr
        else [
            {
                "action": "enable_full_pxr_capabilities",
                "required": False,
                "command": [
                    "python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "usd-core>=24.11,<27",
                ],
            }
        ],
    }
    invalid_config = None
    for field in ("port", "gateway_port"):
        value = config.get(field)
        if value is not None and not 0 <= int(value) <= 65535:
            invalid_config = "invalid_%s" % field
            break
    if invalid_config:
        _fail(
            report,
            exit_code=10,
            stage="configuration_preflight",
            reason=invalid_config,
            next_steps=[
                {
                    "action": "fix_configuration",
                    "command": ["dcc-mcp-openusd", "doctor", "--json"],
                }
            ],
        )
    elif not _version_at_least(core_version, MIN_CORE_VERSION):
        _fail(
            report,
            exit_code=10,
            stage="core_preflight",
            reason="core_version_below_floor",
            next_steps=[
                {
                    "action": "upgrade_core",
                    "command": [
                        "python",
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        "dcc-mcp-core>=%s" % MIN_CORE_VERSION,
                    ],
                }
            ],
        )
    elif detected.has_pxr and not full_capabilities:
        _fail(
            report,
            exit_code=10,
            stage="version_preflight",
            reason="pxr_version_below_floor",
            next_steps=[
                {
                    "action": "upgrade_openusd_runtime",
                    "command": [
                        "python",
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        "usd-core>=24.11,<27",
                    ],
                }
            ],
        )
    elif operation == "verify":
        try:
            report["runtime"]["verification"] = _runtime_smoke(mode)
        except Exception:
            _fail(
                report,
                exit_code=40,
                stage="runtime_verification",
                reason="runtime_smoke_failed",
                next_steps=[
                    {
                        "action": "rerun_verify",
                        "command": ["dcc-mcp-openusd", "verify", "--json"],
                    }
                ],
            )
    return report
