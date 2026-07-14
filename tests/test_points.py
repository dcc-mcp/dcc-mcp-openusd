from __future__ import annotations

import pytest

from dcc_mcp_openusd.runtime import detect_runtime

_HAS_PXR = detect_runtime().has_pxr


@pytest.mark.skipif(not _HAS_PXR, reason="pxr not available")
def test_create_points_authors_portable_fx_prim(tmp_path):
    from dcc_mcp_openusd.runtime import create_points, create_stage

    stage_file = str(tmp_path / "scene.usda")
    create_stage(stage_file)
    result = create_points(
        stage_file,
        "/World/Sparks",
        positions=[[0, 0, 0], [1, 2, 3]],
        widths=[0.1, 0.2],
        colors=[[1, 0.2, 0], [0.1, 0.5, 1]],
        velocities=[[0, 3, 0], [1, 2, 0]],
        ids=[101, 102],
    )

    assert result["point_count"] == 2
    assert result["runtime"] == "pxr"

    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(stage_file)
    points = UsdGeom.Points.Get(stage, "/World/Sparks")
    assert len(points.GetPointsAttr().Get()) == 2
    assert list(points.GetWidthsAttr().Get()) == pytest.approx([0.1, 0.2])
    assert list(points.GetIdsAttr().Get()) == [101, 102]
    assert len(points.GetVelocitiesAttr().Get()) == 2
    display_color = points.GetDisplayColorPrimvar()
    assert display_color.GetInterpolation() == UsdGeom.Tokens.vertex
    assert len(display_color.Get()) == 2
