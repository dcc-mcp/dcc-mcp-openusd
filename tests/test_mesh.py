from __future__ import annotations

import pytest

from dcc_mcp_openusd.runtime import OpenUsdError, create_mesh, create_stage, detect_runtime

_HAS_PXR = detect_runtime().has_pxr


@pytest.mark.skipif(not _HAS_PXR, reason="pxr not available")
def test_create_mesh_authors_portable_polygon_topology(tmp_path):
    stage_file = str(tmp_path / "scene.usda")
    create_stage(stage_file)

    result = create_mesh(
        stage_file,
        "/World/Quad",
        points=[[-1, 0, -1], [1, 0, -1], [1, 0, 1], [-1, 0, 1]],
        face_vertex_counts=[4],
        face_vertex_indices=[0, 1, 2, 3],
        subdivision_scheme="none",
        double_sided=True,
    )

    assert result["point_count"] == 4
    assert result["face_count"] == 1

    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(stage_file)
    mesh = UsdGeom.Mesh.Get(stage, "/World/Quad")
    assert mesh.GetPointsAttr().Get() == [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1)]
    assert mesh.GetFaceVertexCountsAttr().Get() == [4]
    assert mesh.GetFaceVertexIndicesAttr().Get() == [0, 1, 2, 3]
    assert mesh.GetSubdivisionSchemeAttr().Get() == UsdGeom.Tokens.none
    assert mesh.GetDoubleSidedAttr().Get() is True


@pytest.mark.skipif(not _HAS_PXR, reason="pxr not available")
def test_create_mesh_rejects_invalid_topology(tmp_path):
    stage_file = str(tmp_path / "scene.usda")
    create_stage(stage_file)

    with pytest.raises(OpenUsdError, match="sum of face_vertex_counts"):
        create_mesh(
            stage_file,
            "/World/Broken",
            points=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            face_vertex_counts=[3],
            face_vertex_indices=[0, 1],
        )

