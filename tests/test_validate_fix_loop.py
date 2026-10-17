"""validate -> fix -> re-validate loop coverage that runs without pxr.

``tests/e2e/test_validate_fix_loop.py`` covers the same loop under the
``test-openusd`` job, where pxr is always installed. This file covers the
reference-path half against both runtimes so the base install -- which has no
pxr and therefore skips ``tests/e2e`` entirely -- still proves the loop closes
in text-fallback mode.

The loop is driven through the shipped skill entry points, exactly as an agent
would: validate, read ``suggested_fix`` off the issue, dispatch the skill it
names, re-validate. No host USD service or network asset library is involved.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dcc_mcp_openusd.runtime import _FIX_SKILL_BY_CODE, RuntimeInfo, detect_runtime
from tests.validate_fix_loop import (
    ASSET_TEMPLATE,
    BROKEN_REFERENCE,
    SKILL_INDEX,
    code_count,
    dispatch_suggested_fix,
    issue_for_code,
    validate,
)

REAL_HAS_PXR = detect_runtime().has_pxr

BROKEN_PRIM = "/World/SetDressing/MissingSetPiece"


@pytest.fixture(params=["pxr", "text-fallback"])
def runtime_mode(request, monkeypatch):
    """Run the loop once per runtime by forcing the detected runtime."""
    mode = request.param
    if mode == "pxr" and not REAL_HAS_PXR:
        pytest.skip("pxr runtime requested but usd-core is not installed")  # noqa: B028
    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=mode == "pxr"))
    return mode


@pytest.fixture
def stage(tmp_path) -> Path:
    """A mutable copy of the stage whose reference cannot be resolved."""
    target = tmp_path / "scene.usda"
    shutil.copyfile(BROKEN_REFERENCE, target)
    return target


@pytest.fixture
def library(tmp_path) -> Path:
    """An asset library holding a file matching the broken reference basename."""
    root = tmp_path / "library"
    root.mkdir()
    (root / "missing_set_piece.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")
    return root


# ── the catalog contract the loop depends on ───────────────────────────────


def test_every_fix_skill_is_dispatchable():
    """Each code the validator can fix maps to a tool an agent can actually call."""
    assert SKILL_INDEX, "the bundled tools.yaml catalog resolved to no tools"
    for code, skill in _FIX_SKILL_BY_CODE.items():
        assert skill in SKILL_INDEX, f"{code} points at '{skill}', which no bundled skill declares"


# ── the reference loop, in both runtimes ───────────────────────────────────


def test_reference_issue_advertises_a_dispatchable_fix(runtime_mode, stage):
    """The validator names the fix skill and the prim the fix must target."""
    envelope = validate(stage)
    assert code_count(envelope, "UNRESOLVED_REFERENCE") == 1

    issue = issue_for_code(envelope, "UNRESOLVED_REFERENCE")
    suggested = issue["suggested_fix"]
    assert suggested["skill"] == _FIX_SKILL_BY_CODE["UNRESOLVED_REFERENCE"] == "openusd_stage__fix_reference_path"
    assert suggested["args"]["stage_file"] == str(stage)
    assert suggested["args"]["prim_path"] == BROKEN_PRIM
    assert suggested["skill"] in SKILL_INDEX


def test_reference_loop_closes(runtime_mode, stage, library):
    """validate -> fix_reference_path -> re-validate takes UNRESOLVED_REFERENCE 1 -> 0."""
    before = validate(stage)
    assert code_count(before, "UNRESOLVED_REFERENCE") == 1
    assert before["context"]["runtime"] == runtime_mode

    issue = issue_for_code(before, "UNRESOLVED_REFERENCE")
    fix = dispatch_suggested_fix(issue, search_dirs=[str(library)], apply=True)
    assert fix["success"] is True, fix.get("error")
    assert fix["postcondition"]["verified"] is True
    assert fix["postcondition"]["method"] == "stage_readback"

    after = validate(stage)
    assert code_count(after, "UNRESOLVED_REFERENCE") == 0
    assert after["context"]["summary"]["error"] == 0


def test_reference_issue_persists_without_the_fix(runtime_mode, stage, library):
    """A dry run reports a plan and leaves the stage exactly as broken as it was."""
    before = validate(stage)
    assert code_count(before, "UNRESOLVED_REFERENCE") == 1

    issue = issue_for_code(before, "UNRESOLVED_REFERENCE")
    dry_run = dispatch_suggested_fix(issue, search_dirs=[str(library)])
    assert dry_run["success"] is True
    assert dry_run["context"]["targets"][0]["status"] == "planned"

    after = validate(stage)
    assert code_count(after, "UNRESOLVED_REFERENCE") == 1


def test_reference_apply_without_a_replacement_fails_and_changes_nothing(runtime_mode, stage):
    """An apply with nothing to write fails instead of reporting a clean stage."""
    before = validate(stage)
    issue = issue_for_code(before, "UNRESOLVED_REFERENCE")

    fix = dispatch_suggested_fix(issue, apply=True)
    assert fix["success"] is False
    assert fix["error"] == "reference_unresolved"
    assert fix.get("postcondition") is None

    after = validate(stage)
    assert code_count(after, "UNRESOLVED_REFERENCE") == 1, "a failed apply must leave the issue in place"
