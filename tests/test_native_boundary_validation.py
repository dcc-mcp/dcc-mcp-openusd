"""Real USD regressions for dependency completeness and instancer semantics."""

from __future__ import annotations

import zipfile

import pytest

from dcc_mcp_openusd.runtime import OpenUsdError, package_usdz, validate_stage

pxr = pytest.importorskip("pxr")
from pxr import Gf, Sdf, Usd, UsdGeom, UsdVol  # noqa: E402


def stage_at(path):
    stage = Usd.Stage.CreateNew(str(path))
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    UsdGeom.SetStageUpAxis(stage, "Z")
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    return stage


def volume_at(path, asset="missing.vdb", connected=True):
    stage = stage_at(path)
    volume = UsdVol.Volume.Define(stage, "/World/Smoke")
    field = UsdVol.OpenVDBAsset.Define(stage, "/World/Smoke/Density")
    field.CreateFilePathAttr(Sdf.AssetPath(asset))
    field.CreateFieldNameAttr("density")
    if connected:
        volume.CreateFieldRelationship("density", field.GetPath())
    stage.GetRootLayer().Save()
    return stage, field


def instancer_at(path):
    stage = stage_at(path)
    instancer = UsdGeom.PointInstancer.Define(stage, "/World/Scatter")
    UsdGeom.Sphere.Define(stage, "/World/Scatter/Ball")
    instancer.CreatePrototypesRel().SetTargets(["/World/Scatter/Ball"])
    instancer.CreateProtoIndicesAttr([0, 0, 0])
    instancer.CreatePositionsAttr([(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    stage.GetRootLayer().Save()
    return stage, instancer


def issues(path, code):
    return [issue for issue in validate_stage(str(path))["issues"] if issue["code"] == code]


def test_connected_missing_vdb_is_error(tmp_path):
    path = tmp_path / "volume.usda"
    stage, _ = volume_at(path)
    result = validate_stage(str(path))
    assert not result["success"]
    assert issues(path, "UNRESOLVED_VOLUME_ASSET")[0]["location"]["path"] == "/World/Smoke/Density"
    assert stage


def test_unused_optional_asset_is_not_volume_error(tmp_path):
    path = tmp_path / "volume.usda"
    stage, _ = volume_at(path, connected=False)
    stage.GetPrimAtPath("/World").CreateAttribute("optionalAsset", Sdf.ValueTypeNames.Asset).Set(
        Sdf.AssetPath("optional.bin")
    )
    stage.GetRootLayer().Save()
    assert validate_stage(str(path))["success"]


def test_volume_missing_later_sample_is_detected(tmp_path):
    path = tmp_path / "volume.usda"
    (tmp_path / "exists.vdb").write_bytes(b"dependency-only fixture; no grid decoding claimed")
    stage, field = volume_at(path, "exists.vdb")
    field.GetFilePathAttr().Set(Sdf.AssetPath("exists.vdb"), 1)
    field.GetFilePathAttr().Set(Sdf.AssetPath("missing.vdb"), 25)
    stage.GetRootLayer().Save()
    assert "25" in issues(path, "UNRESOLVED_VOLUME_ASSET")[0]["message"]


def test_volume_sublayer_relative_dependency_resolves(tmp_path):
    subdir = tmp_path / "assets"
    subdir.mkdir()
    (subdir / "density.vdb").write_bytes(b"dependency-only fixture")
    sub, _ = volume_at(subdir / "volume.usda", "density.vdb")
    root = stage_at(tmp_path / "root.usda")
    root.GetRootLayer().subLayerPaths.append("assets/volume.usda")
    root.GetRootLayer().Save()
    assert not issues(tmp_path / "root.usda", "UNRESOLVED_VOLUME_ASSET")
    assert sub


def test_unloaded_payload_is_not_forced_into_validation(tmp_path):
    sub, _ = volume_at(tmp_path / "payload.usda")
    root = stage_at(tmp_path / "root.usda")
    root.DefinePrim("/World/Deferred").GetPayloads().AddPayload("payload.usda", "/World")
    root.GetRootLayer().Save()
    assert validate_stage(str(tmp_path / "root.usda"))["success"]
    assert sub


def test_package_missing_dependency_rejects_without_overwriting(tmp_path):
    path = tmp_path / "volume.usda"
    stage, _ = volume_at(path)
    output = tmp_path / "out.usdz"
    output.write_bytes(b"keep existing output")
    with pytest.raises(OpenUsdError, match="missing.vdb"):
        package_usdz(str(path), str(output))
    assert output.read_bytes() == b"keep existing output"
    assert stage


def test_complete_package_has_dependency_and_reopens(tmp_path):
    path = tmp_path / "volume.usda"
    (tmp_path / "density.vdb").write_bytes(b"dependency-only fixture")
    stage, _ = volume_at(path, "density.vdb")
    output = tmp_path / "out.usdz"
    result = package_usdz(str(path), str(output))
    assert result["complete"] is True
    assert result["unresolved_assets"] == []
    assert any(name.endswith("density.vdb") for name in zipfile.ZipFile(output).namelist())
    assert Usd.Stage.Open(str(output))
    assert stage


@pytest.mark.parametrize(
    "attribute,values",
    [
        ("positions", [(0, 0, 0), (1, 0, 0)]),
        ("ids", [7, 8]),
        ("scales", [(1, 1, 1)]),
        ("orientations", [Gf.Quath(1)]),
        ("velocities", [(0, 0, 1)]),
        ("protoIndices", [0, 0, 7]),
    ],
)
def test_instancer_parallel_arrays_and_index_bounds(tmp_path, attribute, values):
    path = tmp_path / "particles.usda"
    stage, instancer = instancer_at(path)
    instancer.GetPrim().GetAttribute(attribute).Set(values, 25)
    stage.GetRootLayer().Save()
    assert issues(path, "INVALID_POINT_INSTANCER")
    assert not validate_stage(str(path))["success"]


def test_valid_sparse_samples_optional_arrays_masks_and_int64_ids(tmp_path):
    path = tmp_path / "particles.usda"
    stage, pi = instancer_at(path)
    pi.GetPositionsAttr().Clear()
    pi.GetPositionsAttr().Set([(0, 0, 0), (1, 0, 0), (2, 0, 0)], 1)
    pi.GetPositionsAttr().Set([(0, 1, 0), (1, 1, 0), (2, 1, 0)], 25)
    pi.CreateIdsAttr([11, 2**40 + 7, 42])
    pi.CreateInvisibleIdsAttr().Set([42], 13)
    pi.CreateScalesAttr([])
    stage.GetRootLayer().Save()
    assert not issues(path, "INVALID_POINT_INSTANCER")
    assert len(pi.ComputeInstanceTransformsAtTime(13, 13)) == 2


def test_empty_instancer_arrays_are_valid(tmp_path):
    path = tmp_path / "particles.usda"
    stage, pi = instancer_at(path)
    pi.GetPositionsAttr().Set([])
    pi.GetProtoIndicesAttr().Set([])
    stage.GetRootLayer().Save()
    assert not issues(path, "INVALID_POINT_INSTANCER")


def test_missing_prototype_target_is_detected(tmp_path):
    path = tmp_path / "particles.usda"
    stage, pi = instancer_at(path)
    pi.GetPrototypesRel().SetTargets(["/World/Missing"])
    stage.GetRootLayer().Save()
    assert "Prototype target" in issues(path, "INVALID_POINT_INSTANCER")[0]["message"]


def test_valid_unloaded_prototype_payload_is_not_missing(tmp_path):
    path = tmp_path / "particles.usda"
    payload = stage_at(tmp_path / "prototype.usda")
    UsdGeom.Sphere.Define(payload, "/World/Ball")
    payload.GetRootLayer().Save()
    stage, pi = instancer_at(path)
    stage.GetPrimAtPath("/World/Scatter/Ball").GetPayloads().AddPayload("prototype.usda", "/World")
    stage.GetRootLayer().Save()
    assert not issues(path, "INVALID_POINT_INSTANCER")


@pytest.mark.parametrize("failure", ["false", "exception"])
def test_native_package_failure_does_not_fallback_or_overwrite(tmp_path, monkeypatch, failure):
    path = tmp_path / "scene.usda"
    stage = stage_at(path)
    stage.GetRootLayer().Save()
    # Fault injection only for this defensive branch; dependency discovery,
    # positive packaging and semantic regression tests use the real USD APIs.
    from pxr import UsdUtils

    def fail_package(*args):
        if failure == "exception":
            raise RuntimeError("injected native failure")
        return False

    monkeypatch.setattr(UsdUtils, "CreateNewUsdzPackage", fail_package)
    output = tmp_path / "output.usdz"
    output.write_bytes(b"preserve")
    with pytest.raises(OpenUsdError, match="packaging failed"):
        package_usdz(str(path), str(output))
    assert output.read_bytes() == b"preserve"


def test_inactive_missing_volume_is_ignored(tmp_path):
    path = tmp_path / "volume.usda"
    stage, _ = volume_at(path)
    stage.GetPrimAtPath("/World/Smoke").SetActive(False)
    stage.GetRootLayer().Save()
    assert not issues(path, "UNRESOLVED_VOLUME_ASSET")
