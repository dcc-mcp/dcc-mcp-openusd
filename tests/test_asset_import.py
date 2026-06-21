"""Tests for the asset_import contract adapters (asset_source / import_to_scene).

These tests run without the pxr Pixar USD runtime so they exercise the
text-fallback path and are fast enough for CI.  The contract objects come from
dcc_mcp_core.asset_import — the module that PIP-1924 (Guido) authored.
"""

from __future__ import annotations

import pytest
from dcc_mcp_core.asset_import import (
    AssetDescriptor,
    AssetFileVariant,
    AssetFormat,
    AxisHint,
    ImportToSceneRequest,
    ImportToSceneResult,
    PlacementHint,
    UnitHint,
)

from dcc_mcp_openusd.runtime import (
    asset_source,
    create_stage,
    import_to_scene,
    list_stage,
)

# ---------------------------------------------------------------------------
# asset_source — builds an AssetDescriptor from a USD file
# ---------------------------------------------------------------------------


def test_asset_source_returns_descriptor_with_usd_variant(tmp_path):
    stage_file = tmp_path / "hero.usda"
    create_stage(str(stage_file), name="hero", up_axis="Y", meters_per_unit=1.0)

    descriptor = asset_source(str(stage_file))

    assert isinstance(descriptor, AssetDescriptor)
    assert descriptor.asset_id == "hero"
    assert len(descriptor.variants) == 1
    variant = descriptor.variants[0]
    assert variant.format == AssetFormat.USD
    assert variant.preferred is True
    assert variant.local_path == str(stage_file.resolve())


def test_asset_source_custom_asset_id(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="scene")

    descriptor = asset_source(str(stage_file), asset_id="custom_hero")

    assert descriptor.asset_id == "custom_hero"


def test_asset_source_reads_up_axis_from_text_fallback(tmp_path):
    stage_file = tmp_path / "z_up.usda"
    create_stage(str(stage_file), name="z_up", up_axis="Z", meters_per_unit=0.01)

    descriptor = asset_source(str(stage_file))

    assert descriptor.up_axis == "z"


def test_asset_source_reads_meters_per_unit(tmp_path):
    stage_file = tmp_path / "cm_stage.usda"
    create_stage(str(stage_file), name="cm", up_axis="Y", meters_per_unit=0.01)

    descriptor = asset_source(str(stage_file))

    # 0.01 meters/unit = centimeter
    assert descriptor.unit_hint == UnitHint.CENTIMETER
    assert abs(descriptor.meters_per_unit - 0.01) < 1e-9


def test_asset_source_usdz_variant_format(tmp_path):
    from dcc_mcp_openusd.runtime import package_usdz

    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="scene")
    usdz_file = tmp_path / "scene.usdz"
    package_usdz(str(stage_file), str(usdz_file))

    descriptor = asset_source(str(usdz_file))

    assert descriptor.variants[0].format == AssetFormat.USDZ


def test_asset_source_descriptor_validates(tmp_path):
    stage_file = tmp_path / "valid.usda"
    create_stage(str(stage_file), name="valid")

    descriptor = asset_source(str(stage_file))

    # validate() must not raise — descriptor is well-formed
    descriptor.validate()


def test_asset_source_missing_file_raises(tmp_path):
    from dcc_mcp_openusd.runtime import OpenUsdError

    with pytest.raises(OpenUsdError):
        asset_source(str(tmp_path / "nonexistent.usda"))


# ---------------------------------------------------------------------------
# import_to_scene — wires an AssetDescriptor into a USD stage
# ---------------------------------------------------------------------------


def _make_descriptor(local_path: str, asset_id: str = "hero") -> AssetDescriptor:
    return AssetDescriptor(
        asset_id=asset_id,
        variants=[AssetFileVariant(local_path=local_path, format=AssetFormat.USD, preferred=True)],
        up_axis=AxisHint.Y,
        unit_hint=UnitHint.METER,
    )


def test_import_to_scene_reference_arc(tmp_path):
    asset_stage = tmp_path / "asset.usda"
    create_stage(str(asset_stage), name="asset")

    scene_stage = tmp_path / "scene.usda"
    create_stage(str(scene_stage), name="scene")

    descriptor = _make_descriptor(str(asset_stage))
    request = ImportToSceneRequest(descriptor=descriptor)
    result = import_to_scene(str(scene_stage), request)

    assert isinstance(result, ImportToSceneResult)
    assert result.success is True
    assert len(result.imported_nodes) == 1
    assert "/World/hero" in result.imported_nodes

    # The reference should be visible in the stage text
    content = scene_stage.read_text(encoding="utf-8")
    assert "asset.usda" in content


def test_import_to_scene_custom_prim_path(tmp_path):
    asset_stage = tmp_path / "prop.usda"
    create_stage(str(asset_stage), name="prop")

    scene_stage = tmp_path / "scene.usda"
    create_stage(str(scene_stage), name="scene")

    descriptor = _make_descriptor(str(asset_stage), asset_id="prop")
    request = ImportToSceneRequest(descriptor=descriptor)
    result = import_to_scene(str(scene_stage), request, target_prim_path="/World/Props/Prop01")

    assert result.success is True
    assert "/World/Props/Prop01" in result.imported_nodes


def test_import_to_scene_payload_arc(tmp_path):

    asset_stage = tmp_path / "heavy.usda"
    create_stage(str(asset_stage), name="heavy")

    scene_stage = tmp_path / "scene.usda"
    create_stage(str(scene_stage), name="scene")

    descriptor = _make_descriptor(str(asset_stage), asset_id="heavy")
    request = ImportToSceneRequest(descriptor=descriptor, extra={"usd_arc": "payload"})

    # payload requires pxr; without it we expect an OpenUsdError propagated
    # as a failure result (not a Python exception)
    from dcc_mcp_openusd.runtime import detect_runtime

    if detect_runtime().has_pxr:
        result = import_to_scene(str(scene_stage), request)
        assert result.success is True
    else:
        result = import_to_scene(str(scene_stage), request)
        assert result.success is False
        assert result.error_message is not None


def test_import_to_scene_skip_existing(tmp_path):
    asset_stage = tmp_path / "asset.usda"
    create_stage(str(asset_stage), name="asset")

    scene_stage = tmp_path / "scene.usda"
    create_stage(str(scene_stage), name="scene")

    descriptor = _make_descriptor(str(asset_stage))
    request = ImportToSceneRequest(descriptor=descriptor, skip_existing=True)

    # First import
    result1 = import_to_scene(str(scene_stage), request)
    assert result1.success is True

    # Second import with skip_existing=True
    result2 = import_to_scene(str(scene_stage), request)
    assert result2.success is True
    # Should have a warning about skipping
    assert any("skip" in w.message.lower() or "exist" in w.message.lower() for w in result2.warnings)


def test_import_to_scene_no_usd_variant_fails():
    """Descriptor with no USD/USDZ variant should return a failure result."""
    descriptor = AssetDescriptor(
        asset_id="fbx_only",
        variants=[AssetFileVariant(local_path="/tmp/mesh.fbx", format=AssetFormat.FBX, preferred=True)],
    )
    request = ImportToSceneRequest(descriptor=descriptor)

    # We need a stage file path but it won't be reached
    result = import_to_scene("/nonexistent/scene.usda", request)

    assert result.success is False
    assert result.error_message is not None
    assert "USD" in result.error_message or "usd" in result.error_message.lower()


def test_import_to_scene_placement_hint_text_fallback(tmp_path):
    from dcc_mcp_openusd.runtime import detect_runtime

    if detect_runtime().has_pxr:
        pytest.skip("placement text-fallback path requires no pxr")

    asset_stage = tmp_path / "asset.usda"
    create_stage(str(asset_stage), name="asset")

    scene_stage = tmp_path / "scene.usda"
    create_stage(str(scene_stage), name="scene")

    descriptor = _make_descriptor(str(asset_stage))
    request = ImportToSceneRequest(
        descriptor=descriptor,
        placement=PlacementHint(translate=[1.0, 2.0, 3.0]),
    )
    result = import_to_scene(str(scene_stage), request)

    # Even if xformOp application fails on text-fallback, the import itself must succeed
    assert result.success is True


# ---------------------------------------------------------------------------
# round-trip: asset_source → import_to_scene
# ---------------------------------------------------------------------------


def test_round_trip_source_then_import(tmp_path):
    """Build a descriptor from a stage file and import it into another stage."""
    source_stage = tmp_path / "source.usda"
    create_stage(str(source_stage), name="source", up_axis="Y", meters_per_unit=1.0)

    target_stage = tmp_path / "target.usda"
    create_stage(str(target_stage), name="target")

    descriptor = asset_source(str(source_stage))
    request = ImportToSceneRequest(descriptor=descriptor)
    result = import_to_scene(str(target_stage), request)

    assert result.success is True
    assert len(result.imported_nodes) >= 1

    listing = list_stage(str(target_stage))
    prim_paths = {p["path"] for p in listing["prims"]}
    assert any(descriptor.asset_id in p for p in prim_paths)
