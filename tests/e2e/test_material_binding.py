"""E2E: Material binding golden path — UsdPreviewSurface connect + bind + pxr verify."""

from __future__ import annotations

import pytest

pxr = pytest.importorskip("pxr")
from pxr import Sdf, Usd, UsdShade


def test_material_binding_golden_path(tmp_path):
    """Create Material → Preview Surface → bind → pxr verify material binding relationship."""
    from dcc_mcp_openusd.runtime import create_stage

    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="material_test")

    stage = Usd.Stage.Open(str(stage_file))

    # Define Material with UsdPreviewSurface shader
    material_path = Sdf.Path("/World/TestMaterial")
    material = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(stage, material_path.AppendChild("PreviewShader"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((1.0, 0.3, 0.3))
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    # Define a Mesh and bind the material
    mesh_path = Sdf.Path("/World/TestMesh")
    stage.DefinePrim(mesh_path, "Mesh")
    UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(mesh_path)).Bind(material)

    stage.GetRootLayer().Save()

    # ── Reopen and verify ──
    stage2 = Usd.Stage.Open(str(stage_file))

    # Material prim with correct type
    material_prim = stage2.GetPrimAtPath("/World/TestMaterial")
    assert material_prim.IsValid()
    assert material_prim.GetTypeName() == "Material"

    # UsdShade Material API — surface output exists and is connected
    material_api = UsdShade.Material(material_prim)
    surface_output = material_api.GetSurfaceOutput()
    assert surface_output is not None
    assert surface_output.HasConnectedSource()

    # Shader prim with UsdPreviewSurface id
    shader_prim = stage2.GetPrimAtPath("/World/TestMaterial/PreviewShader")
    assert shader_prim.IsValid()
    assert shader_prim.GetTypeName() == "Shader"
    shader_api = UsdShade.Shader(shader_prim)
    assert shader_api.GetIdAttr().Get() == "UsdPreviewSurface"

    # Material binding on Mesh
    mesh_prim = stage2.GetPrimAtPath("/World/TestMesh")
    assert mesh_prim.IsValid()
    binding_api = UsdShade.MaterialBindingAPI(mesh_prim)
    bound_material, _ = binding_api.ComputeBoundMaterial()
    assert bound_material.GetPath() == material_path
