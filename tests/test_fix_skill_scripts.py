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
