"""fix_reference_path coverage.

The repair path must behave identically with and without pxr, because the
rewrite is a text authoring operation and the readback reuses the shared fact
collector. Every behavioural test therefore runs against both runtimes by
monkeypatching the cached ``RuntimeInfo``. No test needs a host USD service or
a network asset library: fixtures are written into ``tmp_path``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dcc_mcp_openusd.runtime import (
    RuntimeInfo,
    detect_runtime,
    find_unresolved_references,
    fix_reference_path,
    validate_stage,
)
from tests.conftest import binary_stage, headerless_stage  # noqa: F401  (shared stage builders)

REAL_HAS_PXR = detect_runtime().has_pxr

DATA_DIR = Path(__file__).parent / "data" / "usd"
BROKEN_REFERENCE = DATA_DIR / "broken_reference.usda"
BROKEN_PRIM = "/World/SetDressing/MissingSetPiece"
BROKEN_ASSET = "./assets/missing_set_piece.usda"

ASSET_TEMPLATE = (
    '#usda 1.0\n(\n    defaultPrim = "Prop"\n    metersPerUnit = 1\n    upAxis = "Y"\n)\n\ndef Mesh "Prop"\n{\n}\n'
)


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
    """A copy of the broken-reference sample stage, safe to mutate."""
    target = tmp_path / "scene.usda"
    shutil.copyfile(BROKEN_REFERENCE, target)
    return target


@pytest.fixture
def library(tmp_path) -> Path:
    """An asset library holding a file matching the broken basename."""
    root = tmp_path / "library" / "assets"
    root.mkdir(parents=True)
    (root / "missing_set_piece.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")
    return root


def _statuses(result) -> dict:
    return {target["prim_path"]: target["status"] for target in result["targets"]}


# ── discovery ──────────────────────────────────────────────────────────────


def test_broken_reference_is_discovered(runtime_mode, stage):
    """Discovery reports the prim, the authored asset path and what it resolved to."""
    result = find_unresolved_references(str(stage))

    assert result["count"] == 1
    assert result["unresolved"][0]["prim_path"] == BROKEN_PRIM
    assert result["unresolved"][0]["asset_path"] == BROKEN_ASSET
    assert result["unresolved"][0]["basename"] == "missing_set_piece.usda"


def test_discovery_agrees_with_validate_stage(runtime_mode, stage):
    """The fix skill and the validator judge the same references."""
    unresolved = {entry["prim_path"] for entry in find_unresolved_references(str(stage))["unresolved"]}
    reported = {
        issue["location"]["path"]
        for issue in validate_stage(str(stage))["issues"]
        if issue["code"] == "UNRESOLVED_REFERENCE"
    }
    assert unresolved == reported


def test_healthy_stage_has_nothing_to_fix(runtime_mode, tmp_path):
    """A stage with no broken reference reports no targets instead of inventing one."""
    target = tmp_path / "scene.usda"
    shutil.copyfile(BROKEN_REFERENCE, target)
    (tmp_path / "assets").mkdir()
    shutil.copyfile(BROKEN_REFERENCE, tmp_path / "assets" / "missing_set_piece.usda")

    result = fix_reference_path(str(target))
    assert result["targets"] == []
    assert result["applied"] is False


# ── dry run ────────────────────────────────────────────────────────────────


def test_dry_run_reports_a_plan_without_touching_the_stage(runtime_mode, stage, library):
    """apply=False finds the replacement, reports it, and writes nothing."""
    before = stage.read_text(encoding="utf-8")

    result = fix_reference_path(str(stage), search_dirs=[str(library)])

    assert result["applied"] is False
    assert _statuses(result) == {BROKEN_PRIM: "planned"}
    assert result["targets"][0]["replacement"].endswith("missing_set_piece.usda")
    assert result["unresolved"] == []
    assert stage.read_text(encoding="utf-8") == before


def test_dry_run_without_a_library_is_explicitly_unresolved(runtime_mode, stage):
    """No replacement and no search dirs is 'unresolved', never a silent success."""
    result = fix_reference_path(str(stage))

    assert _statuses(result) == {BROKEN_PRIM: "unresolved"}
    assert result["unresolved"]
    assert result["failed"] == []
    assert result["applied"] is False


# ── applying a fix ─────────────────────────────────────────────────────────


def test_apply_rewrites_the_reference_and_validates_clean(runtime_mode, stage, library):
    """Applying a found replacement fixes the reference the validator reported."""
    result = fix_reference_path(str(stage), search_dirs=[str(library)], apply=True)

    assert result["applied"] is True
    assert result["verified"] is True
    assert _statuses(result) == {BROKEN_PRIM: "fixed"}
    assert result["failed"] == []
    assert BROKEN_ASSET not in stage.read_text(encoding="utf-8")

    codes = {issue["code"] for issue in validate_stage(str(stage))["issues"]}
    assert "UNRESOLVED_REFERENCE" not in codes


def test_apply_accepts_an_explicit_replacement_asset(runtime_mode, stage, tmp_path):
    """An explicit asset_path is used without any search."""
    replacement = tmp_path / "replacement.usda"
    replacement.write_text(ASSET_TEMPLATE, encoding="utf-8")

    result = fix_reference_path(str(stage), prim_path=BROKEN_PRIM, asset_path=str(replacement), apply=True)

    assert _statuses(result) == {BROKEN_PRIM: "fixed"}
    assert result["targets"][0]["replacement"] == "replacement.usda"
    assert result["verified"] is True


def test_explicit_replacement_must_exist_on_disk(runtime_mode, stage, tmp_path):
    """A replacement path that does not exist fails instead of authoring a broken path."""
    missing = tmp_path / "nope.usda"

    result = fix_reference_path(str(stage), prim_path=BROKEN_PRIM, asset_path=str(missing), apply=True)

    assert result["applied"] is False
    assert result["failed"], "a missing replacement must be reported, not skipped"
    assert "does not exist" in result["failed"][0]["detail"]
    assert BROKEN_ASSET in stage.read_text(encoding="utf-8"), "the stage must be left untouched"


def test_explicit_replacement_is_rejected_when_several_are_broken(runtime_mode, tmp_path):
    """An explicit replacement cannot stand in for several broken references."""
    target = tmp_path / "scene.usda"
    other = tmp_path / "other.usda"
    target.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Xform "A" (\n        prepend references = @./gone_a.usda@\n    )\n    {\n    }\n'
        '    def Xform "B" (\n        prepend references = @./gone_b.usda@\n    )\n    {\n    }\n'
        "}\n",
        encoding="utf-8",
    )
    other.write_text(ASSET_TEMPLATE, encoding="utf-8")

    result = fix_reference_path(str(target), asset_path=str(other), apply=True)

    assert result["applied"] is False
    assert len(result["failed"]) == 2
    assert "asset_path" in result["failed"][0]["detail"]
    assert "gone_a.usda" in target.read_text(encoding="utf-8"), "nothing may be rewritten"
    assert "gone_b.usda" in target.read_text(encoding="utf-8")


def test_apply_is_idempotent(runtime_mode, stage, library):
    """A second run finds nothing left to fix."""
    first = fix_reference_path(str(stage), search_dirs=[str(library)], apply=True)
    assert first["applied"] is True

    second = fix_reference_path(str(stage), search_dirs=[str(library)], apply=True)
    assert second["targets"] == []
    assert second["applied"] is False


def test_rewrite_only_touches_the_prim_that_owns_the_reference(runtime_mode, tmp_path, library):
    """A child prim referencing the same broken asset keeps its own authoring."""
    target = tmp_path / "scene.usda"
    target.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Xform "Parent" (\n        prepend references = @./assets/missing_set_piece.usda@\n    )\n'
        "    {\n"
        '        def Xform "Child" (\n            prepend references = @./assets/missing_set_piece.usda@\n        )\n'
        "        {\n        }\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = fix_reference_path(str(target), prim_path="/World/Parent", search_dirs=[str(library)], apply=True)

    assert _statuses(result) == {"/World/Parent": "fixed"}
    text = target.read_text(encoding="utf-8")
    assert "@./assets/missing_set_piece.usda@" in text, "the child's own reference must survive"
    remaining = find_unresolved_references(str(target), prim_path="/World/Parent/Child")
    assert remaining["count"] == 1


# ── no silent success ──────────────────────────────────────────────────────


def test_a_prim_filter_that_matches_nothing_is_not_a_clean_stage(runtime_mode, stage, library):
    """A filter with no match reports no targets; the stage itself is still broken."""
    result = fix_reference_path(str(stage), prim_path="/World/Nope", search_dirs=[str(library)], apply=True)

    assert result["applied"] is False
    assert not result["targets"], "a prim with no broken reference is simply not a target"
    assert result["failed"] == []
    # The unfiltered stage still has its broken reference, so "no targets" must
    # never be read as "the stage is clean".
    assert find_unresolved_references(str(stage))["count"] == 1


def test_unresolved_targets_are_listed_separately(runtime_mode, stage):
    """Unresolved targets are surfaced for the caller and never counted as fixed."""
    result = fix_reference_path(str(stage), apply=True)

    assert result["applied"] is False
    assert [target["prim_path"] for target in result["unresolved"]] == [BROKEN_PRIM]
    assert result["verified"] is False


def test_search_dirs_that_do_not_exist_are_skipped(runtime_mode, stage, library, tmp_path):
    """A missing search root never raises and never hides a real candidate."""
    result = fix_reference_path(
        str(stage),
        search_dirs=[str(tmp_path / "absent"), str(library)],
        apply=True,
    )

    assert _statuses(result) == {BROKEN_PRIM: "fixed"}


def test_comment_text_is_preserved_by_the_rewrite(runtime_mode, stage, library):
    """Rewriting a reference must not strip comments from the layer."""
    commented = stage.parent / "commented.usda"
    commented.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        "    # set dressing lives here\n"
        '    def Xform "Piece" (\n'
        "        prepend references = @./assets/missing_set_piece.usda@  # fix me\n"
        "    )\n    {\n    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = fix_reference_path(str(commented), search_dirs=[str(library)], apply=True)
    text = commented.read_text(encoding="utf-8")

    assert _statuses(result) == {"/World/Piece": "fixed"}
    assert "# set dressing lives here" in text
    assert "# fix me" in text


# ── one replacement cannot stand in for several broken references ───────────


def _two_references_on_one_prim(tmp_path) -> Path:
    """A stage whose single prim authors two broken references."""
    target = tmp_path / "scene.usda"
    target.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Xform "A" (\n        prepend references = [@./gone_a.usda@, @./gone_b.usda@]\n    )\n'
        "    {\n    }\n"
        "}\n",
        encoding="utf-8",
    )
    return target


def test_asset_path_is_rejected_for_two_references_on_one_prim(runtime_mode, tmp_path):
    """Giving prim_path must not bypass the ambiguity guard.

    The filter narrows the *prim*, not the reference: one prim can author
    several broken references, and a single asset_path silently collapsing them
    into one would drop a reference while still reading back as fixed.
    """
    target = _two_references_on_one_prim(tmp_path)
    replacement = tmp_path / "replacement.usda"
    replacement.write_text(ASSET_TEMPLATE, encoding="utf-8")

    result = fix_reference_path(str(target), prim_path="/World/A", asset_path=str(replacement), apply=True)

    assert result["applied"] is False
    assert result["failed"], "two broken references must not be collapsed into one"
    assert "gone_a.usda" in target.read_text(encoding="utf-8")
    assert "gone_b.usda" in target.read_text(encoding="utf-8")


def test_search_hit_is_rejected_when_it_would_collapse_two_references(runtime_mode, tmp_path):
    """The same collapse via search_dirs is rejected before anything is written."""
    target = tmp_path / "scene.usda"
    # Two references with the same basename in different directories: a
    # basename search can only ever return one candidate for both.
    target.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\ndef Xform "World"\n{\n    def Xform "A" (\n        prepend references = [@./x/gone.usda@, @./y/gone.usda@]\n    )\n    {\n    }\n}',
        encoding="utf-8",
    )
    library = tmp_path / "library"
    library.mkdir()
    (library / "gone.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")

    result = fix_reference_path(str(target), search_dirs=[str(library)], apply=True)

    assert result["applied"] is False
    assert result["failed"], "one search hit cannot replace two distinct references"
    text = target.read_text(encoding="utf-8")
    assert "@./x/gone.usda@" in text and "@./y/gone.usda@" in text


def test_distinct_replacements_do_not_collide(runtime_mode, tmp_path):
    """Distinct replacements for one prim's two references are still accepted."""
    target = _two_references_on_one_prim(tmp_path)
    replacement = tmp_path / "replacement.usda"
    replacement.write_text(ASSET_TEMPLATE, encoding="utf-8")

    first = fix_reference_path(str(target), prim_path="/World/A", asset_path=str(replacement), apply=True)
    assert first["failed"], "the ambiguous case is still rejected first"

    # Fixing them one at a time is possible because each pass sees one target.
    text = target.read_text(encoding="utf-8").replace("@./gone_a.usda@", "@./replacement.usda@")
    target.write_text(text, encoding="utf-8")
    (tmp_path / "replacement.usda").write_text(ASSET_TEMPLATE, encoding="utf-8")

    second = fix_reference_path(str(target), prim_path="/World/A", asset_path=str(replacement), apply=True)
    assert second["applied"] is True
    assert second["failed"] == []


def test_verified_is_false_when_any_target_failed(runtime_mode, tmp_path):
    """A partial fix does not report top-level verified success."""
    target = _two_references_on_one_prim(tmp_path)
    replacement = tmp_path / "replacement.usda"
    replacement.write_text(ASSET_TEMPLATE, encoding="utf-8")

    result = fix_reference_path(str(target), prim_path="/World/A", asset_path=str(replacement), apply=True)
    assert result["verified"] is False


# ── commented-out references are left alone ────────────────────────────────


def test_commented_out_reference_is_not_rewritten(runtime_mode, tmp_path, library):
    """Only live references are rewritten; a commented-out one keeps its text."""
    target = tmp_path / "scene.usda"
    target.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        "    # prepend references = @./assets/missing_set_piece.usda@\n"
        '    def Xform "Piece" (\n'
        "        prepend references = @./assets/missing_set_piece.usda@\n"
        "    )\n    {\n    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = fix_reference_path(str(target), prim_path="/World/Piece", search_dirs=[str(library)], apply=True)
    text = target.read_text(encoding="utf-8")

    assert _statuses(result) == {"/World/Piece": "fixed"}
    assert "# prepend references = @./assets/missing_set_piece.usda@" in text


def test_binary_layer_without_pxr_is_not_reported_clean(tmp_path, monkeypatch):
    """A binary layer the collector cannot read must not look like a clean stage."""
    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=False))
    stage = binary_stage(tmp_path)

    result = fix_reference_path(str(stage))

    assert result["applied"] is False
    assert result["failed"], "an unreadable layer is neither clean nor fixed"
    assert "binary" in result["failed"][0]["detail"]


def test_binary_layer_is_still_rejected_when_apply_is_requested(tmp_path, monkeypatch):
    """The same refusal holds for apply=true, not just a dry run."""
    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=False))
    stage = binary_stage(tmp_path)

    result = fix_reference_path(str(stage), apply=True)

    assert result["applied"] is False
    assert result["failed"]


def test_a_file_that_is_not_a_usd_layer_is_not_reported_clean(runtime_mode, tmp_path):
    """A text file with no #usda header yields no facts; that is not a clean stage."""
    stage = headerless_stage(tmp_path)

    result = fix_reference_path(str(stage))

    assert result["applied"] is False
    assert result["failed"], "an unparseable file must not be reported as having no broken references"


def test_binary_layer_with_a_partial_pxr_install_is_not_clean(partial_pxr, tmp_path):
    """pxr reports usable but the collector never ran: the layer was not inspected.

    detect_runtime() only imports pxr.Usd, while the collector needs pxr.Sdf. A
    broken install therefore reports has_pxr=True and still leaves the facts
    empty, which must not be read as a stage with nothing wrong with it.
    """
    stage = binary_stage(tmp_path)

    result = fix_reference_path(str(stage))

    assert result["applied"] is False
    assert result["failed"], "an unread binary layer is neither clean nor fixed"
    assert "binary" in result["failed"][0]["detail"]
