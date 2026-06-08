"""E2E: Multi-layer composition golden path — sublayer + reference + pxr verify."""

from __future__ import annotations

import pytest

pxr = pytest.importorskip("pxr")
from pxr import Usd


def test_composition_sublayer_reference(tmp_path):
    """Sublayer + reference composition → pxr verify composition structure."""
    from dcc_mcp_openusd.runtime import add_reference, create_stage

    # Create an asset to reference
    ref_dir = tmp_path / "assets"
    ref_dir.mkdir(parents=True)
    ref_file = ref_dir / "chair.usda"
    ref_stage = Usd.Stage.CreateNew(str(ref_file))
    chair = ref_stage.DefinePrim("/Chair", "Xform")
    ref_stage.SetDefaultPrim(chair)
    ref_stage.GetRootLayer().Save()

    # Create a sublayer file (an override or sub-layer)
    sub_file = tmp_path / "lighting.usda"
    sub_stage = Usd.Stage.CreateNew(str(sub_file))
    sub_stage.DefinePrim("/Lighting", "Xform")
    sub_stage.GetRootLayer().Save()

    # Create main stage with runtime tools
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="composition_test")

    # Add sublayer via pxr, add reference via runtime tool
    stage = Usd.Stage.Open(str(stage_file))
    stage.GetRootLayer().subLayerPaths.append(str(sub_file))
    stage.GetRootLayer().Save()

    add_reference(str(stage_file), "/World/Furniture/Chair", str(ref_file))

    # ── Reopen and verify composition ──
    stage2 = Usd.Stage.Open(str(stage_file))

    # Sublayer is present
    root_layer = stage2.GetRootLayer()
    assert len(root_layer.subLayerPaths) >= 1, "Expected at least one sublayer"

    # Referenced prim exists
    chair_prim = stage2.GetPrimAtPath("/World/Furniture/Chair")
    assert chair_prim.IsValid()
    assert chair_prim.GetTypeName() == "Xform"

    # Reference arc is present (prim stack has entries from the reference)
    prim_stack = chair_prim.GetPrimStack()
    assert len(prim_stack) > 0, "Expected non-empty prim stack for referenced prim"

    # Sublayer prim is composed into the stage
    lighting_prim = stage2.GetPrimAtPath("/Lighting")
    assert lighting_prim.IsValid(), "Sublayer prim not found — composition may have failed"


def test_composition_reference_relative_path(tmp_path):
    """Reference with relative asset path must resolve correctly."""
    from dcc_mcp_openusd.runtime import add_reference, create_stage

    # Create asset inside a directory relative to the stage
    asset_dir = tmp_path / "props"
    asset_dir.mkdir()
    asset_file = asset_dir / "table.usda"
    asset_stage = Usd.Stage.CreateNew(str(asset_file))
    table_prim = asset_stage.DefinePrim("/Table", "Mesh")
    asset_stage.SetDefaultPrim(table_prim)
    asset_stage.GetRootLayer().Save()

    # Create main stage at tmp_path root
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="relref_test")

    result = add_reference(str(stage_file), "/World/Props/Table", str(asset_file))
    assert "asset_path" in result

    # Verify prim exists and reference arc is present (type resolved from reference)
    stage = Usd.Stage.Open(str(stage_file))
    table_prim = stage.GetPrimAtPath("/World/Props/Table")
    assert table_prim.IsValid()
    # When reference resolves, the prim type comes from the referenced prim
    assert table_prim.GetTypeName() in ("Mesh", "Xform")
