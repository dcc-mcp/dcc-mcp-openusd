"""E2E: validate -> fix -> re-validate agent loop.

These tests drive the loop the way an agent does, and nothing else: call the
``openusd_validate__validate_stage`` tool, read ``suggested_fix`` off the
returned issue, dispatch the named skill through its shipped ``tools.yaml``
entry point, then re-validate and assert the targeted rule code disappeared.
No step hand-rolls a repair, so a broken dispatch or a ``suggested_fix`` that
stops naming a real skill fails here instead of silently passing.

Every test also asserts the negative case: on the same broken stage, with no
fix applied, the targeted code is still there. That keeps a test that never
actually validated anything from reading as a pass.

The material apply path needs pxr, which this directory's ``conftest.py``
already guarantees. The reference-path loop works without pxr as well and is
covered against both runtimes in ``tests/test_validate_fix_loop.py``.

No host USD service and no network asset library are involved: fixtures are
copied into ``tmp_path`` and the replacement asset is written locally.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pxr = pytest.importorskip("pxr")

from dcc_mcp_openusd.runtime import _FIX_SKILL_BY_CODE  # noqa: E402
from tests.validate_fix_loop import (  # noqa: E402
    ASSET_TEMPLATE,
    BROKEN_REFERENCE,
    SKILL_INDEX,
    UNBOUND_MATERIAL,
    call_skill,
    code_count,
    dispatch_suggested_fix,
    issue_for_code,
    validate,
)


@pytest.fixture
def broken_reference_stage(tmp_path) -> Path:
    """A mutable copy of the stage whose reference cannot be resolved."""
    target = tmp_path / "scene.usda"
    shutil.copyfile(BROKEN_REFERENCE, target)
    return target


@pytest.fixture
def reference_library(tmp_path) -> Path:
    """An asset library holding a file matching the broken reference basename."""
    library = tmp_path / "library"
    library.mkdir()
    (library / "missing_set_piece.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")
    return library


@pytest.fixture
def unbound_material_stage(tmp_path) -> Path:
    """A mutable copy of the stage with a dangling binding and an unbound material."""
    target = tmp_path / "scene.usda"
    shutil.copyfile(UNBOUND_MATERIAL, target)
    return target


# ── the catalog contract the loop depends on ───────────────────────────────


def test_every_fix_skill_is_dispatchable():
    """Each code the validator can fix maps to a tool an agent can actually call."""
    assert SKILL_INDEX, "the bundled tools.yaml catalog resolved to no tools"
    for code, skill in _FIX_SKILL_BY_CODE.items():
        assert skill in SKILL_INDEX, f"{code} points at '{skill}', which no bundled skill declares"


# ── UNRESOLVED_REFERENCE ───────────────────────────────────────────────────


def test_reference_loop_closes(broken_reference_stage, reference_library):
    """validate -> fix_reference_path -> re-validate takes UNRESOLVED_REFERENCE 1 -> 0."""
    before = validate(broken_reference_stage)
    assert code_count(before, "UNRESOLVED_REFERENCE") == 1

    issue = issue_for_code(before, "UNRESOLVED_REFERENCE")
    fix = dispatch_suggested_fix(issue, search_dirs=[str(reference_library)], apply=True)
    assert fix["success"] is True, fix.get("error")
    assert fix["postcondition"]["verified"] is True

    after = validate(broken_reference_stage)
    assert code_count(after, "UNRESOLVED_REFERENCE") == 0
    assert after["context"]["summary"]["error"] == 0


def test_reference_issue_persists_without_the_fix(broken_reference_stage, reference_library):
    """The same stage stays broken across two validations when nothing is applied.

    Without this, a validator that reported nothing would still let the loop
    test above pass on its final assert.
    """
    before = validate(broken_reference_stage)
    assert code_count(before, "UNRESOLVED_REFERENCE") == 1

    # A dry run is what an agent does before committing to a write: it must
    # report a plan and leave the stage exactly as broken as it found it.
    issue = issue_for_code(before, "UNRESOLVED_REFERENCE")
    dry_run = dispatch_suggested_fix(issue, search_dirs=[str(reference_library)])
    assert dry_run["success"] is True
    assert dry_run["context"]["targets"][0]["status"] == "planned"

    after = validate(broken_reference_stage)
    assert code_count(after, "UNRESOLVED_REFERENCE") == 1


# ── material rules ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("code", ["DANGLING_MATERIAL_BINDING", "UNBOUND_MATERIAL"])
def test_material_issues_advertise_a_dispatchable_fix(unbound_material_stage, code):
    """Both material rules carry a suggested_fix naming the material fix skill."""
    envelope = validate(unbound_material_stage)
    assert code_count(envelope, code) == 1

    issue = issue_for_code(envelope, code)
    suggested = issue["suggested_fix"]
    assert suggested["skill"] == _FIX_SKILL_BY_CODE[code] == "openusd_material__suggest_material_bind"
    assert suggested["args"]["stage_file"] == str(unbound_material_stage)
    assert suggested["skill"] in SKILL_INDEX


@pytest.mark.parametrize("code", ["DANGLING_MATERIAL_BINDING", "UNBOUND_MATERIAL"])
def test_material_loop_closes(unbound_material_stage, code):
    """validate -> suggest_material_bind -> apply -> re-validate takes the code 1 -> 0."""
    before = validate(unbound_material_stage)
    assert code_count(before, code) == 1

    issue = issue_for_code(before, code)

    # The validator knows the code, not which prim/material pair to bind; the
    # skill answers that. Take its first bindable candidate instead of picking
    # one here, so the agent still owns the decision rather than the test.
    suggestion = dispatch_suggested_fix(issue)
    assert suggestion["success"] is True
    candidates = suggestion["context"]["suggestions"]
    assert candidates, "the fix skill must offer a binding for this issue"
    chosen = next(item for item in candidates if item["auto_bindable"])

    applied = call_skill(
        issue["suggested_fix"]["skill"],
        stage_file=str(unbound_material_stage),
        prim_path=chosen["prim_path"],
        material_path=chosen["material_path"],
        apply=True,
    )
    assert applied["success"] is True, applied.get("error")
    assert applied["postcondition"]["verified"] is True

    after = validate(unbound_material_stage)
    assert code_count(after, code) == 0


@pytest.mark.parametrize("code", ["DANGLING_MATERIAL_BINDING", "UNBOUND_MATERIAL"])
def test_material_issues_persist_without_the_fix(unbound_material_stage, code):
    """A dry-run suggestion writes nothing, so both material codes remain."""
    before = validate(unbound_material_stage)
    assert code_count(before, code) == 1

    issue = issue_for_code(before, code)
    dispatch_suggested_fix(issue)

    after = validate(unbound_material_stage)
    assert code_count(after, code) == 1
    assert code_count(after, "DANGLING_MATERIAL_BINDING") == 1
    assert code_count(after, "UNBOUND_MATERIAL") == 1


def test_material_loop_does_not_report_a_write_it_could_not_make(unbound_material_stage, monkeypatch):
    """Without pxr the apply step fails loudly instead of reporting a clean stage."""
    from dcc_mcp_openusd.runtime import RuntimeInfo

    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=False))

    before = validate(unbound_material_stage)
    issue = issue_for_code(before, "DANGLING_MATERIAL_BINDING")

    applied = call_skill(
        issue["suggested_fix"]["skill"],
        stage_file=str(unbound_material_stage),
        prim_path="/World/Prop",
        material_path="/World/Materials/PropPaint",
        apply=True,
    )
    assert applied["success"] is False
    assert applied["error"] == "material_bind_failed"
    assert applied.get("postcondition") is None, "a failed apply must not advertise readback evidence"

    after = validate(unbound_material_stage)
    assert code_count(after, "DANGLING_MATERIAL_BINDING") == 1, "a failed apply must leave the issue in place"
