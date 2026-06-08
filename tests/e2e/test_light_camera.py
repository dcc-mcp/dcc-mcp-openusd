"""E2E: Light + Camera golden path — UsdGeomCamera / UsdLux schema verification with pxr."""

from __future__ import annotations

import pytest

pxr = pytest.importorskip("pxr")
from pxr import Gf, Usd, UsdGeom, UsdLux


def test_light_camera_golden_path(tmp_path):
    """Create Camera + Light → pxr verify UsdGeomCamera / UsdLux schema."""
    from dcc_mcp_openusd.runtime import create_stage

    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="light_camera_test")

    stage = Usd.Stage.Open(str(stage_file))

    # Create Camera via UsdGeom
    camera = UsdGeom.Camera.Define(stage, "/World/MainCamera")
    camera.CreateFocalLengthAttr().Set(35.0)
    camera.CreateFocusDistanceAttr().Set(100.0)
    camera.CreateFStopAttr().Set(2.8)

    # Create SphereLight via UsdLux
    light = UsdLux.SphereLight.Define(stage, "/World/KeyLight")
    light.CreateIntensityAttr().Set(500.0)
    light.CreateColorAttr().Set(Gf.Vec3f(1.0, 0.9, 0.8))
    light.CreateExposureAttr().Set(0.0)

    stage.GetRootLayer().Save()

    # ── Reopen and verify ──
    stage2 = Usd.Stage.Open(str(stage_file))

    # Verify Camera schema
    camera_prim = stage2.GetPrimAtPath("/World/MainCamera")
    assert camera_prim.IsValid()
    assert camera_prim.GetTypeName() == "Camera"
    camera_schema = UsdGeom.Camera(camera_prim)
    assert camera_schema.GetFocalLengthAttr().Get() == 35.0
    assert camera_schema.GetFocusDistanceAttr().Get() == 100.0
    assert camera_schema.GetFStopAttr().Get() == pytest.approx(2.8)

    # Verify UsdLux SphereLight schema
    light_prim = stage2.GetPrimAtPath("/World/KeyLight")
    assert light_prim.IsValid()
    assert light_prim.GetTypeName() == "SphereLight"
    light_schema = UsdLux.SphereLight(light_prim)
    assert light_schema.GetIntensityAttr().Get() == 500.0
    assert light_schema.GetColorAttr().Get() == Gf.Vec3f(1.0, 0.9, 0.8)
    assert light_schema.GetExposureAttr().Get() == 0.0

    # Verify both are under /World
    children = stage2.GetPrimAtPath("/World").GetChildren()
    child_paths = {str(c.GetPath()) for c in children}
    assert "/World/MainCamera" in child_paths
    assert "/World/KeyLight" in child_paths
