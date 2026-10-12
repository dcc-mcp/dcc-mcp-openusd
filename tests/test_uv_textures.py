"""Native, save/reopen coverage for portable UV and texture authoring."""

from __future__ import annotations

import base64
import shutil
import zipfile

import pytest

from dcc_mcp_openusd import runtime as rt

_HAS_PXR = rt.detect_runtime().has_pxr
UVS = [[0, 0], [1, 0], [1, 1], [0, 1]]
MAT = "/World/Mat"
MESH = "/World/Quad"


@pytest.fixture
def scene(tmp_path):
    if not _HAS_PXR:
        pytest.skip("pxr not available")
    path = tmp_path / "scene.usda"
    rt.create_stage(str(path))
    rt.create_mesh(str(path), MESH, [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [4], [0, 1, 2, 3])
    rt.create_material(str(path), MAT)
    rt.create_preview_surface(str(path), MAT, roughness=0.25)
    rt.bind_material(str(path), MESH, MAT)
    texture = tmp_path / "textures" / "color.png"
    texture.parent.mkdir()
    texture.write_bytes(
        base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN8sAAAAASUVORK5CYII=")
    )
    return path, texture


def test_indexed_uvs_reopen_and_replace_without_stale_indices(scene):
    from pxr import Sdf, Usd, UsdGeom

    path, _ = scene
    result = rt.set_mesh_uvs(str(path), MESH, UVS, indices=[0, 1, 2, 3])
    assert result["runtime"] == "pxr"
    assert result["indexed"] is True
    stage = Usd.Stage.Open(str(path))
    pv = UsdGeom.PrimvarsAPI(stage.GetPrimAtPath(MESH)).GetPrimvar("st")
    assert pv.GetTypeName() == Sdf.ValueTypeNames.TexCoord2fArray
    assert pv.GetInterpolation() == "faceVarying"
    assert list(pv.GetIndices()) == [0, 1, 2, 3]
    assert [tuple(v) for v in pv.ComputeFlattened()] == [tuple(v) for v in UVS]
    del pv, stage
    rt.set_mesh_uvs(str(path), MESH, UVS, interpolation="vertex")
    stage = Usd.Stage.Open(str(path))
    pv = UsdGeom.PrimvarsAPI(stage.GetPrimAtPath(MESH)).GetPrimvar("st")
    assert not pv.IsIndexed()
    assert pv.GetInterpolation() == "vertex"
    assert len(pv.ComputeFlattened()) == 4


def test_texture_network_reopen_and_idempotent_update(scene):
    from pxr import Sdf, Usd, UsdShade

    path, texture = scene
    rt.set_mesh_uvs(str(path), MESH, UVS)
    result = rt.connect_preview_surface_texture(str(path), MAT, "textures/color.png")
    assert result["texture_asset_path"] == "textures/color.png"
    assert result["source_color_space"] == "sRGB"
    assert result["channel"] == "rgb"
    again = rt.connect_preview_surface_texture(str(path), MAT, str(texture), input_name="diffuseColor")
    assert again == result
    stage = Usd.Stage.Open(str(path))
    shader = UsdShade.Shader.Get(stage, MAT + "/Shader")
    node, output, kind = shader.GetInput("diffuseColor").GetConnectedSource()
    assert str(node.GetPath()) == result["texture_path"]
    assert output == "rgb" and kind == UsdShade.AttributeType.Output
    tex = UsdShade.Shader(node.GetPrim())
    assert tex.GetIdAttr().Get() == "UsdUVTexture"
    assert tex.GetOutput("rgb").GetTypeName() == Sdf.ValueTypeNames.Float3
    assert tex.GetInput("file").Get().resolvedPath == str(texture)
    reader_api, output, _ = tex.GetInput("st").GetConnectedSource()
    reader = UsdShade.Shader(reader_api.GetPrim())
    assert reader.GetIdAttr().Get() == "UsdPrimvarReader_float2"
    assert reader.GetInput("varname").GetTypeName() == Sdf.ValueTypeNames.String
    assert reader.GetInput("varname").Get() == "st"
    assert output == "result"
    assert shader.GetInput("roughness").Get() == pytest.approx(0.25)
    assert len([p for p in stage.Traverse() if p.GetTypeName() == "Shader"]) == 3
    assert not stage.GetCompositionErrors()


def test_texture_and_uvs_survive_relocation_and_usdz(scene, tmp_path):
    from pxr import Usd, UsdShade, UsdUtils

    path, texture = scene
    rt.set_mesh_uvs(str(path), MESH, UVS)
    result = rt.connect_preview_surface_texture(str(path), MAT, str(texture))
    moved = tmp_path / "relocated"
    moved.mkdir()
    shutil.copy2(path, moved / path.name)
    shutil.copytree(texture.parent, moved / "textures")
    stage = Usd.Stage.Open(str(moved / path.name))
    tex = UsdShade.Shader.Get(stage, result["texture_path"])
    assert tex.GetInput("file").Get().resolvedPath == str(moved / "textures" / texture.name)
    package = tmp_path / "asset.usdz"
    assert UsdUtils.CreateNewUsdzPackage(str(path), str(package))
    with zipfile.ZipFile(package) as archive:
        assert any(name.endswith("color.png") for name in archive.namelist())
    packaged = Usd.Stage.Open(str(package))
    assert packaged and not packaged.GetCompositionErrors()
    assert UsdShade.Shader.Get(packaged, result["texture_path"]).GetInput("file").Get().resolvedPath


@pytest.mark.parametrize(
    "input_name,channel", [("roughness", "r"), ("metallic", "b"), ("opacity", "a"), ("normal", "rgb")]
)
def test_data_textures_use_raw_and_typed_channels(scene, input_name, channel):
    from pxr import Sdf, Usd, UsdShade

    path, texture = scene
    result = rt.connect_preview_surface_texture(str(path), MAT, str(texture), input_name=input_name, channel=channel)
    stage = Usd.Stage.Open(str(path))
    tex = UsdShade.Shader.Get(stage, result["texture_path"])
    assert tex.GetInput("sourceColorSpace").Get() == "raw"
    shader = UsdShade.Shader.Get(stage, MAT + "/Shader")
    expected = Sdf.ValueTypeNames.Normal3f if input_name == "normal" else Sdf.ValueTypeNames.Float
    assert shader.GetInput(input_name).GetTypeName() == expected
    if input_name == "normal":
        assert tuple(tex.GetInput("scale").Get()) == (2, 2, 2, 1)
        assert tuple(tex.GetInput("bias").Get()) == (-1, -1, -1, 0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"uvs": UVS[:3]},
        {"uvs": UVS, "indices": [0, 1, 2, 4]},
        {"uvs": UVS, "indices": [0, 1, 2]},
        {"uvs": UVS, "indices": [0, 1, 2, 3.2]},
        {"uvs": [[0, 0], [1, 0], [1, 1], [float("nan"), 1]]},
        {"uvs": UVS, "interpolation": "varying"},
        {"uvs": UVS, "primvar_name": "primvars:st"},
    ],
)
def test_invalid_uvs_do_not_mutate_file(scene, kwargs):
    path, _ = scene
    before = path.read_bytes()
    with pytest.raises(rt.OpenUsdError):
        rt.set_mesh_uvs(str(path), MESH, **kwargs)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_name": "unknown"},
        {"channel": "r"},
        {"input_name": "roughness", "channel": "rgb"},
        {"input_name": "normal", "source_color_space": "sRGB"},
        {"source_color_space": "linear"},
        {"texcoord_name": "primvars:st"},
        {"wrap_s": "unknown"},
        {"shader_path": "/World/Absent"},
    ],
)
def test_invalid_texture_arguments_do_not_mutate_file(scene, kwargs):
    path, texture = scene
    before = path.read_bytes()
    with pytest.raises(rt.OpenUsdError):
        rt.connect_preview_surface_texture(str(path), MAT, str(texture), **kwargs)
    assert path.read_bytes() == before


def test_missing_texture_and_wrong_node_fail_without_mutation(scene):
    from pxr import Usd, UsdShade

    path, texture = scene
    before = path.read_bytes()
    with pytest.raises(rt.OpenUsdError, match="Texture file"):
        rt.connect_preview_surface_texture(str(path), MAT, "missing.png")
    assert path.read_bytes() == before
    stage = Usd.Stage.Open(str(path))
    UsdShade.Shader.Define(stage, MAT + "/Shader_diffuseColorTexture").CreateIdAttr("OtherShader")
    stage.GetRootLayer().Save()
    del stage
    before = path.read_bytes()
    with pytest.raises(rt.OpenUsdError, match="already exists"):
        rt.connect_preview_surface_texture(str(path), MAT, str(texture))
    assert path.read_bytes() == before


def test_sublayer_override_preserves_source_and_blocks_inherited_indices(scene, tmp_path):
    from pxr import Usd, UsdGeom, UsdShade

    source, texture = scene
    rt.set_mesh_uvs(str(source), MESH, UVS, indices=[0, 1, 2, 3])
    first = rt.connect_preview_surface_texture(str(source), MAT, str(texture))
    source_bytes = source.read_bytes()
    shot = tmp_path / "shot.usda"
    rt.create_stage(str(shot))
    rt.add_sublayer(str(shot), str(source))
    rt.set_mesh_uvs(str(shot), MESH, UVS, interpolation="vertex")
    rt.connect_preview_surface_texture(str(shot), MAT, str(texture), source_color_space="raw", texcoord_name="detailUV")
    stage = Usd.Stage.Open(str(shot))
    pv = UsdGeom.PrimvarsAPI(stage.GetPrimAtPath(MESH)).GetPrimvar("st")
    assert not pv.IsIndexed()
    assert len(pv.ComputeFlattened()) == 4
    assert UsdShade.Shader.Get(stage, first["texture_path"]).GetInput("sourceColorSpace").Get() == "raw"
    assert source.read_bytes() == source_bytes


@pytest.mark.parametrize(
    "name,args",
    [
        ("set_mesh_uvs", {"prim_path": MESH, "uvs": UVS}),
        ("connect_preview_surface_texture", {"material_path": MAT, "texture_file": "x.png"}),
    ],
)
def test_new_tools_fail_cleanly_without_pxr(tmp_path, monkeypatch, name, args):
    path = tmp_path / "scene.usda"
    path.write_text("#usda 1.0\n")
    monkeypatch.setattr(rt, "_RUNTIME_INFO", rt.RuntimeInfo(has_pxr=False))
    with pytest.raises(rt.OpenUsdError, match="pxr runtime"):
        getattr(rt, name)(stage_file=str(path), **args)


def test_animated_uvs_rejected_without_save(scene):
    from pxr import Usd, UsdGeom

    path, _ = scene
    rt.set_mesh_uvs(str(path), MESH, UVS)
    stage = Usd.Stage.Open(str(path))
    pv = UsdGeom.PrimvarsAPI(stage.GetPrimAtPath(MESH)).GetPrimvar("st")
    pv.Set(pv.Get(), 1)
    stage.GetRootLayer().Save()
    del pv, stage
    before = path.read_bytes()
    with pytest.raises(rt.OpenUsdError, match="Animated UV"):
        rt.set_mesh_uvs(str(path), MESH, UVS)
    assert path.read_bytes() == before


@pytest.mark.parametrize("property_name", ["inputs:varname", "outputs:result"])
def test_connected_reader_properties_rejected_without_save(scene, property_name):
    from pxr import Sdf, Usd

    path, texture = scene
    result = rt.connect_preview_surface_texture(str(path), MAT, str(texture))
    stage = Usd.Stage.Open(str(path))
    reader = stage.GetPrimAtPath(result["primvar_reader_path"])
    reader.GetAttribute(property_name).SetConnections([Sdf.Path("/World/Absent.outputs:value")])
    stage.GetRootLayer().Save()
    del reader, stage
    before = path.read_bytes()
    with pytest.raises(rt.OpenUsdError, match="already exists"):
        rt.connect_preview_surface_texture(str(path), MAT, str(texture))
    assert path.read_bytes() == before


def test_custom_uv_set_and_shader_keep_existing_material_connection(scene):
    from pxr import Usd, UsdGeom, UsdShade

    path, texture = scene
    rt.set_mesh_uvs(str(path), MESH, UVS, primvar_name="detailUV")
    rt.create_preview_surface(str(path), MAT, shader_path=MAT + "/CustomSurface")
    result = rt.connect_preview_surface_texture(str(path), MAT, str(texture), texcoord_name="detailUV")
    assert result["shader_path"] == MAT + "/CustomSurface"
    stage = Usd.Stage.Open(str(path))
    material = UsdShade.Material.Get(stage, MAT)
    assert str(material.ComputeSurfaceSource()[0].GetPath()) == MAT + "/CustomSurface"
    reader = UsdShade.Shader.Get(stage, result["primvar_reader_path"])
    assert reader.GetInput("varname").Get() == "detailUV"
    assert UsdGeom.PrimvarsAPI(stage.GetPrimAtPath(MESH)).GetPrimvar("detailUV")


@pytest.mark.parametrize("absolute_input", [False, True])
def test_parent_directory_textures_remain_relative_after_relocation(scene, tmp_path, absolute_input):
    from pxr import Usd, UsdShade

    source, texture = scene
    layers = tmp_path / "layers"
    layers.mkdir()
    path = layers / "look.usda"
    shutil.copy2(source, path)
    texture_arg = str(texture) if absolute_input else "../textures/color.png"
    result = rt.connect_preview_surface_texture(str(path), MAT, texture_arg)
    assert result["texture_asset_path"] == "../textures/color.png"
    relocated = tmp_path / "relocated_project"
    relocated.mkdir()
    shutil.copytree(layers, relocated / "layers")
    shutil.copytree(texture.parent, relocated / "textures")
    stage = Usd.Stage.Open(str(relocated / "layers" / "look.usda"))
    asset = UsdShade.Shader.Get(stage, result["texture_path"]).GetInput("file").Get()
    assert asset.path == "../textures/color.png"
    assert asset.resolvedPath == str(relocated / "textures" / "color.png")
