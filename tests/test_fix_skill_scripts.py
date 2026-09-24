"""Skill-script envelope coverage for the two fix skills.

These tests load the tool scripts the way the runtime does and assert on the
result envelope rather than on internals, so they prove what an agent actually
receives. They are deliberately offline: no host, no pxr requirement, no asset
library beyond ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from dcc_mcp_openusd.runtime import RuntimeInfo

SCRIPTS = Path(__file__).parents[1] / "src" / "dcc_mcp_openusd" / "skills"
DATA_DIR = Path(__file__).parent / "data" / "usd"

ASSET_TEMPLATE = '#usda 1.0\n(\n    defaultPrim = "Prop"\n)\n\ndef Mesh "Prop"\n{\n}\n'


def _load_script(relative_path: str):
    path = SCRIPTS / relative_path
    spec = importlib.util.spec_from_file_location("openusd_test_tool", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def text_runtime(monkeypatch):
    """Fix skills must work without pxr, so pin the offline runtime."""
    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=False))


# ── fix_reference_path script ──────────────────────────────────────────────


def test_fix_reference_path_reports_success_when_it_repairs(tmp_path):
    """A repaired reference is a success carrying verified readback evidence."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)
    library = tmp_path / "library"
    library.mkdir()
    (library / "missing_set_piece.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")

    result = tool.main(stage_file=str(stage), search_dirs=[str(library)], apply=True)

    assert result["success"] is True
    assert result["error"] is None
    assert result["context"]["targets"][0]["status"] == "fixed"
    assert result["postcondition"]["verified"] is True
    assert result["postcondition"]["method"] == "stage_readback"


def test_fix_reference_path_warns_instead_of_succeeding_silently(tmp_path):
    """A dry run that cannot resolve anything returns success with a warning."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)

    result = tool.main(stage_file=str(stage))

    assert result["success"] is True, "a dry run is not an error"
    assert result["context"]["warning"], "an unresolved reference must be flagged"
    assert "unresolved" in result["context"]["warning"]
    assert result["context"]["unresolved"]


def test_fix_reference_path_fails_when_the_replacement_is_missing(tmp_path):
    """A replacement that does not exist on disk is a failure, not a no-op."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)

    result = tool.main(
        stage_file=str(stage),
        prim_path="/World/SetDressing/MissingSetPiece",
        asset_path=str(tmp_path / "absent.usda"),
        apply=True,
    )

    assert result["success"] is False
    assert result["context"]["failed"]
    assert stage.read_text(encoding="utf-8") == (DATA_DIR / "broken_reference.usda").read_text(encoding="utf-8")


def test_fix_reference_path_reports_a_clean_stage(tmp_path):
    """Nothing broken means nothing to do, reported as a success with no targets."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)
    (tmp_path / "assets").mkdir()
    shutil.copyfile(DATA_DIR / "broken_reference.usda", tmp_path / "assets" / "missing_set_piece.usda")

    result = tool.main(stage_file=str(stage))

    assert result["success"] is True
    assert result["context"].get("warning", "") == ""
    assert result["context"]["targets"] == []


# ── apply=true must never come back as success when it did not fix anything ─


def test_fix_reference_path_fails_when_apply_finds_no_replacement(tmp_path):
    """apply=true with nothing to write is a failure, not a warning success."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)

    result = tool.main(stage_file=str(stage), apply=True)

    assert result["success"] is False, "apply=true promised a fix; warning-success would hide that"
    assert result["error"] == "reference_unresolved"
    assert result["context"]["unresolved"]
    assert stage.read_text(encoding="utf-8") == (DATA_DIR / "broken_reference.usda").read_text(encoding="utf-8")


def test_fix_reference_path_dry_run_does_not_claim_a_write(tmp_path):
    """A dry run that found a replacement must not report a write it never made."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)
    library = tmp_path / "library"
    library.mkdir()
    (library / "missing_set_piece.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")

    result = tool.main(stage_file=str(stage), search_dirs=[str(library)])

    assert result["success"] is True, "a dry run is not an error"
    assert "postcondition" not in result, "no postcondition may claim a write that never happened"
    assert result["context"].get("warning", "") == ""
    assert "apply=true" in result["prompt"]
    assert all(target["status"] == "planned" for target in result["context"]["targets"])
    assert stage.read_text(encoding="utf-8") == (DATA_DIR / "broken_reference.usda").read_text(encoding="utf-8")


def test_fix_reference_path_warns_when_a_prim_filter_matches_nothing(tmp_path):
    """A filter that matched nothing is not the same as a clean stage."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)

    result = tool.main(stage_file=str(stage), prim_path="/World/Nope")

    assert result["success"] is True
    assert result["context"]["warning"], "an unmatched filter must be flagged"
    assert "/World/Nope" in result["context"]["warning"]


# ── suggest_material_bind failure hints match the actual cause ─────────────


def test_missing_arguments_do_not_suggest_installing_pxr(tmp_path):
    """A missing-argument failure must not send the agent to pip install."""
    tool = _load_script("openusd-material/scripts/suggest_material_bind.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "unbound_material.usda", stage)

    result = tool.main(stage_file=str(stage), prim_path="/World/Prop", apply=True)

    assert result["success"] is False
    assert "prim_path" in result["prompt"] and "material_path" in result["prompt"]
    assert "usd-core" not in result["prompt"]
    assert not any("usd-core" in item for item in result["context"]["possible_solutions"])


def test_material_filter_that_matches_nothing_warns(tmp_path):
    """A material filter with no match must not read as a clean stage."""
    tool = _load_script("openusd-material/scripts/suggest_material_bind.py")
    stage = tmp_path / "scene.usda"
    # A healthy stage: the only material is bound, so nothing is left to
    # suggest and an unmatched filter is the one thing worth reporting.
    stage.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Material "Paint"\n    {\n    }\n'
        '    def Mesh "Prop"\n    {\n        rel material:binding = </World/Paint>\n    }\n'
        "}\n",
        encoding="utf-8",
    )

    result = tool.main(stage_file=str(stage), material_path="/World/Materials/Ghost")

    assert result["success"] is True
    assert result["context"]["warning"], "an unmatched filter must be flagged"
    assert "/World/Materials/Ghost" in result["context"]["warning"]


# ── a second apply must stay a success (idempotency) ───────────────────────


def test_fix_reference_path_is_idempotent_at_the_envelope_level(tmp_path):
    """Running apply=true twice is a success both times, not an error on the second."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)
    library = tmp_path / "library"
    library.mkdir()
    (library / "missing_set_piece.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")

    first = tool.main(stage_file=str(stage), search_dirs=[str(library)], apply=True)
    assert first["success"] is True, "the first apply fixes the reference"

    second = tool.main(stage_file=str(stage), search_dirs=[str(library)], apply=True)
    assert second["success"] is True, "a second apply has nothing left to do, which is not a failure"
    assert second["error"] is None
    assert second["context"]["targets"] == []
    assert "No broken references" in second["message"]


def test_apply_on_a_clean_stage_is_a_success(tmp_path):
    """apply=true over a stage that was never broken is a success."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)
    (tmp_path / "assets").mkdir()
    shutil.copyfile(DATA_DIR / "broken_reference.usda", tmp_path / "assets" / "missing_set_piece.usda")

    result = tool.main(stage_file=str(stage), apply=True)

    assert result["success"] is True
    assert result["context"].get("warning", "") == ""


def test_filter_miss_warns_under_apply_too(tmp_path):
    """The unmatched-filter warning is reachable whether or not apply was asked for."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "broken_reference.usda", stage)

    result = tool.main(stage_file=str(stage), prim_path="/World/Nope", apply=True)

    assert result["success"] is True, "a filter that missed is not a failed fix"
    assert result["context"]["warning"]
    assert "/World/Nope" in result["context"]["warning"]


def test_collision_keeps_unrelated_unresolved_targets(tmp_path):
    """A collision on one prim must not hide a target elsewhere that had no candidate."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usda"
    stage.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Xform "A" (\n        prepend references = [@./x/gone.usda@, @./y/gone.usda@]\n    )\n'
        "    {\n    }\n"
        '    def Xform "B" (\n        prepend references = @./nowhere.usda@\n    )\n'
        "    {\n    }\n"
        "}\n",
        encoding="utf-8",
    )
    library = tmp_path / "library"
    library.mkdir()
    (library / "gone.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")

    before = stage.read_text(encoding="utf-8")
    result = tool.main(stage_file=str(stage), search_dirs=[str(library)], apply=True)

    assert result["success"] is False
    prims = [target["prim_path"] for target in result["context"]["targets"]]
    assert "/World/B" in prims, "the target with no candidate must still be reported"
    assert "/World/B" in [target["prim_path"] for target in result["context"]["unresolved"]]
    assert stage.read_text(encoding="utf-8") == before, "a rejected collision must not write anything"


# ── suggest_material_bind script ───────────────────────────────────────────


def test_suggest_material_bind_returns_actionable_suggestions():
    """The envelope carries suggestions the agent can act on without pxr."""
    tool = _load_script("openusd-material/scripts/suggest_material_bind.py")

    result = tool.main(stage_file=str(DATA_DIR / "unbound_material.usda"))

    assert result["success"] is True
    assert result["error"] is None
    suggestions = result["context"]["suggestions"]
    assert {item["reason"] for item in suggestions} >= {"dangling_material_binding", "unbound_material"}
    assert all(item["material_path"] for item in suggestions)


def test_suggest_material_bind_warns_when_no_candidate_exists(tmp_path):
    """A stage with nothing bindable warns instead of reporting empty success."""
    tool = _load_script("openusd-material/scripts/suggest_material_bind.py")
    stage = tmp_path / "scene.usda"
    stage.write_text(
        '#usda 1.0\n(\n    defaultPrim = "Looks"\n)\n\ndef Scope "Looks"\n{\n'
        '    def Material "Paint"\n    {\n    }\n}\n',
        encoding="utf-8",
    )

    result = tool.main(stage_file=str(stage))

    assert result["success"] is True
    assert result["context"]["warning"], "no candidate must be flagged, never silently accepted"
    assert result["context"]["unresolved"]


def test_suggest_material_bind_fails_when_applying_without_pxr(tmp_path):
    """apply=true without pxr is an explicit failure, not a silent success."""
    tool = _load_script("openusd-material/scripts/suggest_material_bind.py")
    stage = tmp_path / "scene.usda"
    shutil.copyfile(DATA_DIR / "unbound_material.usda", stage)

    result = tool.main(
        stage_file=str(stage),
        prim_path="/World/Prop",
        material_path="/World/Materials/PropPaint",
        apply=True,
    )

    assert result["success"] is False
    assert result["error"] == "material_bind_failed"
    assert result["context"]["possible_solutions"]
    assert stage.read_text(encoding="utf-8") == (DATA_DIR / "unbound_material.usda").read_text(encoding="utf-8")


def test_suggest_material_bind_reports_a_clean_stage(tmp_path):
    """A stage with a healthy binding produces no suggestions and no warning."""
    tool = _load_script("openusd-material/scripts/suggest_material_bind.py")
    stage = tmp_path / "scene.usda"
    stage.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\ndef Xform "World"\n{\n'
        '    def Material "Paint"\n    {\n    }\n'
        '    def Mesh "Prop"\n    {\n        rel material:binding = </World/Paint>\n    }\n}\n',
        encoding="utf-8",
    )

    result = tool.main(stage_file=str(stage))

    assert result["success"] is True
    assert result["context"]["suggestions"] == []
    assert result["context"].get("warning", "") == ""


# ── envelope level: an unreadable stage must never look clean ──────────────


def test_fix_reference_path_fails_on_a_binary_stage(tmp_path):
    """The script turns an unreadable layer into an error, not a clean success."""
    tool = _load_script("openusd-stage/scripts/fix_reference_path.py")
    stage = tmp_path / "scene.usdc"
    stage.write_bytes(b"PXR-USDC" + bytes(64))

    result = tool.main(stage_file=str(stage))

    assert result["success"] is False
    assert result["error"] == "reference_fix_failed"
    assert "binary" in result["context"]["failed"][0]["detail"]


def test_suggest_material_bind_fails_on_a_binary_stage(tmp_path):
    """The material skill makes the same refusal."""
    tool = _load_script("openusd-material/scripts/suggest_material_bind.py")
    stage = tmp_path / "scene.usdc"
    stage.write_bytes(b"PXR-USDC" + bytes(64))

    result = tool.main(stage_file=str(stage))

    assert result["success"] is False
    assert result["error"] == "material_bind_failed"
    assert "binary" in result["context"]["failed"][0]["detail"]
