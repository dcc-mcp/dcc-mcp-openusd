"""E2E: Xform animation sampling golden path — time samples write + pxr verify."""

from __future__ import annotations

import pytest

pxr = pytest.importorskip("pxr")
from pxr import Gf, Usd, UsdGeom


def test_xform_animation_golden_path(tmp_path):
    """Write time samples → pxr verify sample times and values."""
    from dcc_mcp_openusd.runtime import create_stage, define_xform

    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="animation_test")

    # Use runtime tool to create xform, then pxr for time-sampled animation
    define_xform(str(stage_file), "/World/AnimatedCube")

    stage = Usd.Stage.Open(str(stage_file))
    xform_prim = stage.GetPrimAtPath("/World/AnimatedCube")
    xform = UsdGeom.Xform(xform_prim)

    # Write time-sampled translate
    translate_op = xform.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
    translate_op.Set(Gf.Vec3d(0.0, 0.0, 0.0), Usd.TimeCode(0.0))
    translate_op.Set(Gf.Vec3d(5.0, 0.0, 0.0), Usd.TimeCode(1.0))
    translate_op.Set(Gf.Vec3d(10.0, 5.0, 0.0), Usd.TimeCode(2.0))

    stage.GetRootLayer().Save()

    # ── Reopen and verify ──
    stage2 = Usd.Stage.Open(str(stage_file))
    xform2 = UsdGeom.Xform(stage2.GetPrimAtPath("/World/AnimatedCube"))

    translate_op2 = xform2.GetTranslateOp()
    assert translate_op2.GetNumTimeSamples() == 3

    # Verify sample times
    sample_times = translate_op2.GetTimeSamples()
    assert 0.0 in sample_times
    assert 1.0 in sample_times
    assert 2.0 in sample_times

    # Verify interpolated values at exact sample times
    assert translate_op2.Get(0.0) == Gf.Vec3d(0.0, 0.0, 0.0)
    assert translate_op2.Get(1.0) == Gf.Vec3d(5.0, 0.0, 0.0)
    assert translate_op2.Get(2.0) == Gf.Vec3d(10.0, 5.0, 0.0)
