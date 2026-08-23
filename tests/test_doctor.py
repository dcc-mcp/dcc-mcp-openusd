"""Public doctor/verify contract tests for the standalone OpenUSD adapter."""

from __future__ import annotations

import json
import os

import dcc_mcp_openusd.doctor as doctor
import dcc_mcp_openusd.runtime as runtime
from dcc_mcp_openusd.cli import main
from dcc_mcp_openusd.runtime import RuntimeInfo


def test_doctor_reports_the_real_runtime_mode_without_overstating_capabilities(capsys) -> None:
    exit_code = main(["doctor", "--json"])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["schema_version"] == "1.0"
    assert report["operation"] == "doctor"
    assert report["directly_usable"] is True
    assert report["requirements"]["min_core_version"] == "0.19.45"
    assert report["requirements"]["min_pxr_version"] == "24.11"
    assert report["runtime"]["mode"] in {"pxr", "text-fallback"}
    if report["runtime"]["mode"] == "pxr":
        assert report["runtime"]["full_capabilities"] is True
        assert report["capabilities"]["native_pxr"] is True
        assert report["capabilities"]["material_binding"] is True
    else:
        assert report["runtime"]["full_capabilities"] is False
        assert report["capabilities"]["native_pxr"] is False
        assert report["capabilities"]["material_binding"] is False
        assert report["capabilities"]["text_usda_authoring"] is True


def test_doctor_rejects_core_below_the_supported_floor(monkeypatch, capsys) -> None:
    monkeypatch.setattr(doctor, "core_version", "0.19.1")

    exit_code = main(["doctor", "--json"])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 10
    assert report["directly_usable"] is False
    assert report["failure"] == {
        "stage": "core_preflight",
        "reason": "core_version_below_floor",
    }
    assert report["next_steps"][0]["action"] == "upgrade_core"


def test_verify_rejects_an_unsupported_pxr_distribution(monkeypatch, capsys) -> None:
    monkeypatch.setattr(doctor, "detect_runtime", lambda: RuntimeInfo(True, "0.23.11"))
    monkeypatch.setattr(doctor, "version", lambda _name: "23.11")

    exit_code = main(["verify", "--json"])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 10
    assert report["runtime"]["mode"] == "pxr"
    assert report["runtime"]["full_capabilities"] is False
    assert report["capabilities"]["native_pxr"] is False
    assert report["failure"] == {
        "stage": "version_preflight",
        "reason": "pxr_version_below_floor",
    }
    assert report["next_steps"][0]["action"] == "upgrade_openusd_runtime"


def test_text_fallback_is_usable_but_never_claims_full_pxr(monkeypatch, capsys) -> None:
    monkeypatch.setattr(runtime, "_RUNTIME_INFO", RuntimeInfo(False))

    exit_code = main(["verify", "--json"])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["directly_usable"] is True
    assert report["runtime"]["mode"] == "text-fallback"
    assert report["runtime"]["full_capabilities"] is False
    assert report["capabilities"]["text_usda_authoring"] is True
    assert report["capabilities"]["native_pxr"] is False
    assert report["capabilities"]["time_sampled_animation"] is False
    assert report["failure"] is None
    assert report["next_steps"] == []
    assert report["optional_next_steps"][0]["action"] == "enable_full_pxr_capabilities"


def test_verify_maps_runtime_smoke_failure_to_stable_exit_40(monkeypatch, capsys) -> None:
    monkeypatch.setattr(runtime, "_RUNTIME_INFO", RuntimeInfo(False))

    def fail_tempdir(*_args, **_kwargs):
        raise OSError("temporary workspace unavailable")

    monkeypatch.setattr(doctor, "TemporaryDirectory", fail_tempdir, raising=False)

    exit_code = main(["verify", "--json"])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 40
    assert report["directly_usable"] is False
    assert report["failure"] == {
        "stage": "runtime_verification",
        "reason": "runtime_smoke_failed",
    }
    assert report["next_steps"][0]["action"] == "rerun_verify"


def test_doctor_reports_daemon_pidfile_and_no_provisioning(tmp_path, capsys) -> None:
    pidfile = tmp_path / "openusd.pid"
    skill_path = tmp_path / "skills"

    exit_code = main(
        [
            "doctor",
            "--json",
            "--daemon",
            "--pidfile",
            str(pidfile),
            "--project-dir",
            str(tmp_path),
            "--metrics",
            "--enable-gateway-failover",
            "--extra-skill-path",
            str(skill_path),
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["daemon"]["requested"] is True
    assert report["daemon"]["pidfile"] == str(pidfile)
    assert report["daemon"]["pidfile_present"] is False
    expected_entry = ["python", "-m", "dcc_mcp_openusd"] if os.name == "nt" else ["dcc-mcp-openusd"]
    assert report["daemon"]["start_command"] == [
        *expected_entry,
        "--daemon",
        "--pidfile",
        str(pidfile),
    ]
    expected_strategy = "verified_process_terminate" if os.name == "nt" else "verified_sigterm"
    expected_signal = None if os.name == "nt" else "SIGTERM"
    assert report["daemon"]["safe_stop"] == {
        "strategy": expected_strategy,
        "signal": expected_signal,
        "verify_process_identity": True,
        "force": False,
        "remove_stale_pidfile_after_exit": os.name == "nt",
    }
    assert report["endpoint"]["requires_external_endpoint"] is False
    assert report["endpoint"]["server_started_by_doctor"] is False
    assert report["endpoint"]["authentication_required"] is False
    assert report["endpoint"]["discovery_command"] == ["dcc-mcp-cli", "list"]
    assert report["configuration"]["project_dir"] == str(tmp_path)
    assert report["configuration"]["metrics_enabled"] is True
    assert report["configuration"]["gateway_failover_enabled"] is True
    assert report["configuration"]["extra_skill_paths"] == [str(skill_path)]
    assert report["configuration"]["file_logging_enabled"] is True
    assert report["provisioning"] == {
        "auto_provision": False,
        "external_payload": None,
        "persistent_adapter_cache": None,
    }


def test_doctor_rejects_invalid_network_configuration(capsys) -> None:
    exit_code = main(["doctor", "--json", "--port", "-1"])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 10
    assert report["directly_usable"] is False
    assert report["failure"] == {
        "stage": "configuration_preflight",
        "reason": "invalid_port",
    }
    assert report["next_steps"][0]["action"] == "fix_configuration"
