"""suggest_material_bind coverage.

Suggestions are built from the shared stage facts, so they must be identical
with and without pxr. Every behavioural test runs against both runtimes; the
``apply`` path needs pxr and is skipped loudly where it is absent, because a
pass that silently did nothing would be the exact failure this skill must
avoid. No host USD service or asset library is required.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dcc_mcp_openusd.runtime import RuntimeInfo, detect_runtime, suggest_material_bind, validate_stage

REAL_HAS_PXR = detect_runtime().has_pxr

DATA_DIR = Path(__file__).parent / "data" / "usd"
UNBOUND_MATERIAL = DATA_DIR / "unbound_material.usda"


@pytest.fixture(params=["pxr", "text-fallback"])
def runtime_mode(request, monkeypatch):
    """Run the test once per runtime by forcing the detected runtime."""
    mode = request.param
    if mode == "pxr" and not REAL_HAS_PXR:
        pytest.skip("pxr runtime requested but usd-core is not installed")  # noqa: B028
    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=mode == "pxr"))
    return mode


@pytest.fixture
def stage(tmp_path) -> Path:
    """A copy of the unbound-material sample stage, safe to mutate."""
    target = tmp_path / "scene.usda"
    shutil.copyfile(UNBOUND_MATERIAL, target)
    return target


def _reasons(result) -> set:
    return {suggestion["reason"] for suggestion in result["suggestions"]}


# ── suggestions ────────────────────────────────────────────────────────────


def test_dangling_binding_suggests_a_real_material(runtime_mode):
    """A binding to a missing material is answered with the materials that exist."""
    result = suggest_material_bind(str(UNBOUND_MATERIAL))

    dangling = [item for item in result["suggestions"] if item["reason"] == "dangling_material_binding"]
    assert len(dangling) == 1
    assert dangling[0]["prim_path"] == "/World/Prop"
    assert dangling[0]["material_path"] == "/World/Materials/PropPaint"
    assert dangling[0]["candidates"] == ["/World/Materials/PropPaint"]
    assert dangling[0]["auto_bindable"] is True


def test_unbound_material_suggests_a_bindable_prim(runtime_mode):
    """A material nobody binds is answered with the prims it could bind to."""
    result = suggest_material_bind(str(UNBOUND_MATERIAL))

    unbound = [item for item in result["suggestions"] if item["reason"] == "unbound_material"]
    assert len(unbound) == 1
    assert unbound[0]["material_path"] == "/World/Materials/PropPaint"
    assert unbound[0]["prim_path"]


def test_suggestions_are_scoped_to_the_requested_prim(runtime_mode):
    """prim_path narrows the report to the prim the caller is fixing."""
    result = suggest_material_bind(str(UNBOUND_MATERIAL), prim_path="/World/Prop")

    assert result["suggestions"], "the requested prim still has issues to report"
    assert {item["prim_path"] for item in result["suggestions"]} == {"/World/Prop"}


def test_suggestions_are_scoped_to_the_requested_material(runtime_mode):
    """material_path narrows the report to that material."""
    result = suggest_material_bind(str(UNBOUND_MATERIAL), material_path="/World/Materials/PropPaint")

    assert result["suggestions"], "the requested material still has issues to report"
    assert {item["material_path"] for item in result["suggestions"]} == {"/World/Materials/PropPaint"}


def test_non_material_binding_target_is_reported_separately(runtime_mode, tmp_path):
    """A binding pointing at a prim that exists but is not a Material gets its own reason."""
    target = tmp_path / "scene.usda"
    target.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Material "Paint"\n    {\n    }\n'
        '    def Xform "NotAMaterial"\n    {\n    }\n'
        '    def Mesh "Prop"\n    {\n        rel material:binding = </World/NotAMaterial>\n    }\n'
        "}\n",
        encoding="utf-8",
    )

    result = suggest_material_bind(str(target))
    bad = [item for item in result["suggestions"] if item["reason"] == "non_material_binding_target"]
    assert len(bad) == 1
    assert bad[0]["prim_path"] == "/World/Prop"
    assert bad[0]["material_path"] == "/World/Paint"


def test_suggestions_cover_the_issues_validate_stage_reports(runtime_mode):
    """Every material issue the validator emits has a matching suggestion."""
    result = suggest_material_bind(str(UNBOUND_MATERIAL))
    codes = {issue["code"] for issue in validate_stage(str(UNBOUND_MATERIAL))["issues"]}

    assert "DANGLING_MATERIAL_BINDING" in codes
    assert "UNBOUND_MATERIAL" in codes
    assert _reasons(result) >= {"dangling_material_binding", "unbound_material"}


def test_clean_stage_has_no_suggestions(runtime_mode, tmp_path):
    """A stage whose material is bound produces nothing to suggest."""
    target = tmp_path / "scene.usda"
    target.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Material "Paint"\n    {\n    }\n'
        '    def Mesh "Prop"\n    {\n        rel material:binding = </World/Paint>\n    }\n'
        "}\n",
        encoding="utf-8",
    )

    result = suggest_material_bind(str(target))
    assert result["suggestions"] == []
    assert result["unresolved"] == []


def test_missing_candidates_are_reported_not_hidden(runtime_mode, tmp_path):
    """With nothing bindable in the stage, the issue is unresolved, not successful."""
    target = tmp_path / "scene.usda"
    # Only a Scope and a Material: a Scope is not a bind target, so the
    # material ends up with no candidate at all.
    target.write_text(
        '#usda 1.0\n(\n    defaultPrim = "Looks"\n)\n\n'
        'def Scope "Looks"\n{\n'
        '    def Material "Paint"\n    {\n    }\n'
        "}\n",
        encoding="utf-8",
    )

    result = suggest_material_bind(str(target))
    assert result["suggestions"], "an unbound material must still be reported"
    assert result["unresolved"]
    assert result["unresolved"][0]["candidates"] == []
    assert result["unresolved"][0]["auto_bindable"] is False


def test_explicit_pair_always_yields_a_suggestion(runtime_mode, stage):
    """A caller that names both sides gets that suggestion even if it is unusual."""
    result = suggest_material_bind(str(stage), prim_path="/World/Prop", material_path="/World/Materials/PropPaint")

    assert result["suggestions"] == [
        {
            "prim_path": "/World/Prop",
            "material_path": "/World/Materials/PropPaint",
            "reason": "explicit_request",
            "detail": "Caller supplied both prim_path and material_path",
            "candidates": ["/World/Materials/PropPaint"],
            "auto_bindable": True,
        }
    ]


def test_suggestions_are_identical_across_runtimes():
    """The suggestion engine is runtime-independent, like every shared rule."""
    if not REAL_HAS_PXR:
        pytest.skip("runtime parity requires usd-core; the test-openusd CI job provides it")  # noqa: B028

    import dcc_mcp_openusd.runtime as runtime_module

    original = runtime_module._RUNTIME_INFO
    try:
        runtime_module._RUNTIME_INFO = RuntimeInfo(has_pxr=True)
        pxr_result = suggest_material_bind(str(UNBOUND_MATERIAL))
        runtime_module._RUNTIME_INFO = RuntimeInfo(has_pxr=False)
        text_result = suggest_material_bind(str(UNBOUND_MATERIAL))
    finally:
        runtime_module._RUNTIME_INFO = original

    assert pxr_result["suggestions"] == text_result["suggestions"]


# ── applying a binding ─────────────────────────────────────────────────────


def test_apply_requires_both_sides(runtime_mode, stage):
    """apply=true without a prim and a material is a failure, not a partial write."""
    result = suggest_material_bind(str(stage), prim_path="/World/Prop", apply=True)

    assert result["applied"] is False
    assert result["failed"], "an incomplete apply must be reported"
    assert "requires both prim_path and material_path" in result["failed"][0]["detail"]


def test_apply_without_pxr_fails_explicitly(stage, monkeypatch, tmp_path):
    """Without pxr the binding cannot be written, so the call fails."""
    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=False))
    result = suggest_material_bind(
        str(stage),
        prim_path="/World/Prop",
        material_path="/World/Materials/PropPaint",
        apply=True,
    )

    assert result["applied"] is False
    assert result["verified"] is False
    assert len(result["failed"]) == 1
    assert "pxr" in result["failed"][0]["detail"]
    assert stage.read_text(encoding="utf-8") == UNBOUND_MATERIAL.read_text(encoding="utf-8")


def test_apply_writes_a_binding_that_validate_stage_accepts(stage):
    """Applied bindings survive a re-read and clear the dangling-binding error."""
    if not REAL_HAS_PXR:
        pytest.skip("applying a binding requires usd-core")  # noqa: B028

    result = suggest_material_bind(
        str(stage),
        prim_path="/World/Prop",
        material_path="/World/Materials/PropPaint",
        apply=True,
    )

    assert result["applied"] is True
    assert result["verified"] is True
    assert result["failed"] == []

    codes = {issue["code"] for issue in validate_stage(str(stage))["issues"]}
    assert "DANGLING_MATERIAL_BINDING" not in codes
    assert "UNBOUND_MATERIAL" not in codes
