"""Binary layers need native metadata, not text-only absence diagnostics."""

from pathlib import Path

import pytest

from dcc_mcp_openusd import runtime


@pytest.fixture
def usd():
    pytest.importorskip("pxr")
    from pxr import Sdf, Usd, UsdGeom, UsdVol

    return Sdf, Usd, UsdGeom, UsdVol


def stage_at(usd, path):
    _, Usd, UsdGeom, _ = usd
    stage = Usd.Stage.CreateNew(str(path))
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    UsdGeom.SetStageUpAxis(stage, "Z")
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Cube.Define(stage, "/World/Cube")
    stage.GetRootLayer().Save()
    return stage


def codes(result):
    return {issue["code"] for issue in result["issues"]}


@pytest.mark.parametrize("suffix", [".usdc", ".usd"])
def test_native_binary_matches_ascii_and_does_not_modify_file(usd, tmp_path, suffix):
    path = tmp_path / ("scene" + suffix)
    stage = stage_at(usd, path)
    ascii_path = tmp_path / "control.usda"
    assert stage.GetRootLayer().Export(str(ascii_path))
    before = path.read_bytes()
    assert before.startswith(b"PXR-USDC")

    result = runtime.validate_stage(str(path), strict=True)
    control = runtime.validate_stage(str(ascii_path), strict=True)

    assert result["runtime"] == "pxr"
    assert result["native_checks"] == "performed"
    assert result["success"] == control["success"] is True
    assert result["issues"] == control["issues"] == []
    assert path.read_bytes() == before


def test_binary_missing_authored_metadata_is_not_filled_from_usd_defaults(usd, tmp_path):
    _, Usd, UsdGeom, _ = usd
    path = tmp_path / "missing.usdc"
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.Xform.Define(stage, "/World")
    stage.GetRootLayer().Save()

    result = runtime.validate_stage(str(path), strict=True)

    assert codes(result) == {"MISSING_DEFAULT_PRIM", "MISSING_UP_AXIS", "MISSING_METERS_PER_UNIT"}
    assert all(issue["severity"] == "error" for issue in result["issues"])
    assert result["native_checks"] == "performed"


def test_binary_invalid_metadata_is_still_reported(usd, tmp_path):
    path = tmp_path / "invalid.usdc"
    stage = stage_at(usd, path)
    layer = stage.GetRootLayer()
    layer.defaultPrim = "Missing"
    layer.pseudoRoot.SetInfo("upAxis", "W")
    layer.pseudoRoot.SetInfo("metersPerUnit", 0.0)
    layer.Save()

    assert codes(runtime.validate_stage(str(path), strict=True)) == {
        "INVALID_DEFAULT_PRIM",
        "INVALID_UP_AXIS",
        "INVALID_METERS_PER_UNIT",
    }


@pytest.mark.parametrize("root_suffix", [".usda", ".usdc"])
@pytest.mark.parametrize("sub_suffix", [".usda", ".usdc"])
@pytest.mark.parametrize("mismatch", [False, True])
def test_mixed_binary_sublayer_metadata_is_checked(usd, tmp_path, root_suffix, sub_suffix, mismatch):
    _, _, UsdGeom, _ = usd
    sub_path = tmp_path / ("sub" + sub_suffix)
    sub = stage_at(usd, sub_path)
    if mismatch:
        UsdGeom.SetStageUpAxis(sub, "Y")
        UsdGeom.SetStageMetersPerUnit(sub, 0.01)
        sub.GetRootLayer().Save()
    root_path = tmp_path / ("root" + root_suffix)
    root = stage_at(usd, root_path)
    root.GetRootLayer().subLayerPaths.append(sub_path.name)
    root.GetRootLayer().Save()

    result = runtime.validate_stage(str(root_path), strict=True)

    assert codes(result) == ({"UP_AXIS_MISMATCH", "METERS_PER_UNIT_MISMATCH"} if mismatch else set())
    assert all(issue["location"]["path"] == sub_path.name for issue in result["issues"])


def test_binary_sublayer_does_not_hide_missing_root_authored_metadata(usd, tmp_path):
    _, Usd, UsdGeom, _ = usd
    sub = stage_at(usd, tmp_path / "sub.usdc")
    root_path = tmp_path / "root.usdc"
    root = Usd.Stage.CreateNew(str(root_path))
    UsdGeom.Xform.Define(root, "/World")
    root.GetRootLayer().subLayerPaths.append("sub.usdc")
    root.GetRootLayer().Save()

    assert codes(runtime.validate_stage(str(root_path), strict=True)) == {
        "MISSING_DEFAULT_PRIM",
        "MISSING_UP_AXIS",
        "MISSING_METERS_PER_UNIT",
    }
    assert sub


@pytest.mark.parametrize("suffix", [".usda", ".usdc"])
def test_native_semantic_checks_still_run(usd, tmp_path, suffix):
    Sdf, _, UsdGeom, UsdVol = usd
    path = tmp_path / ("semantic" + suffix)
    stage = stage_at(usd, path)
    volume = UsdVol.Volume.Define(stage, "/World/Smoke")
    field = UsdVol.OpenVDBAsset.Define(stage, "/World/Smoke/Density")
    field.CreateFilePathAttr(Sdf.AssetPath("missing.vdb"))
    volume.CreateFieldRelationship("density", field.GetPath())
    instancer = UsdGeom.PointInstancer.Define(stage, "/World/Scatter")
    instancer.CreatePrototypesRel().SetTargets(["/World/Cube"])
    instancer.CreatePositionsAttr([(0, 0, 0)])
    instancer.CreateProtoIndicesAttr([7])
    stage.GetRootLayer().Save()

    result = runtime.validate_stage(str(path), strict=True)

    assert not result["success"]
    assert result["native_checks"] == "performed"
    assert codes(result) == {"UNRESOLVED_VOLUME_ASSET", "INVALID_POINT_INSTANCER"}


def binary_stub(tmp_path):
    path = tmp_path / "unreadable.usdc"
    path.write_bytes(b"PXR-USDC" + bytes(64))
    return path


def test_binary_without_pxr_reports_only_runtime_requirement(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "_RUNTIME_INFO", runtime.RuntimeInfo(has_pxr=False))
    result = runtime.validate_stage(str(binary_stub(tmp_path)), strict=True)
    assert result["runtime"] == "text-fallback"
    assert result["native_checks"] == "unavailable"
    assert codes(result) == {"BINARY_LAYER_REQUIRES_PXR"}
    assert "Install usd-core" in result["next_steps"][0]["detail"]


def test_binary_with_partial_pxr_reports_only_runtime_requirement(partial_pxr, tmp_path):
    result = runtime.validate_stage(str(binary_stub(tmp_path)), strict=True)
    assert result["runtime"] == "text-fallback"
    assert result["native_checks"] == "unavailable"
    assert codes(result) == {"BINARY_LAYER_REQUIRES_PXR"}


def test_ascii_with_partial_pxr_keeps_text_fallback(partial_pxr, tmp_path):
    path = tmp_path / "scene.usda"
    path.write_text(
        '#usda 1.0\n(defaultPrim = "World"\nupAxis = "Z"\nmetersPerUnit = 1)\ndef Xform "World" {}\n',
        encoding="utf-8",
    )
    result = runtime.validate_stage(str(path), strict=True)
    assert result["runtime"] == "text-fallback"
    assert result["success"]


def test_corrupt_binary_with_pxr_reports_open_failure_not_install_advice(usd, tmp_path):
    result = runtime.validate_stage(str(binary_stub(tmp_path)), strict=True)
    assert result["runtime"] == "pxr"
    assert result["native_checks"] == "unavailable"
    assert codes(result) == {"STAGE_OPEN_FAILED"}


@pytest.mark.parametrize("failure", ["none", "exception"])
@pytest.mark.parametrize("phase", ["metadata", "prim-collection"])
def test_native_binary_open_failures_do_not_fall_back(usd, monkeypatch, tmp_path, failure, phase):
    Sdf, _, _, _ = usd
    path = tmp_path / "scene.usdc"
    stage = stage_at(usd, path)
    original_open = Sdf.Layer.FindOrOpen
    calls = 0

    def fail_open(*args):
        nonlocal calls
        calls += 1
        if phase == "prim-collection" and calls == 1:
            return original_open(*args)
        if failure == "exception":
            raise RuntimeError("native open failed")
        return None

    monkeypatch.setattr(Sdf.Layer, "FindOrOpen", fail_open)
    result = runtime.validate_stage(str(path), strict=True)
    assert codes(result) == {"STAGE_OPEN_FAILED"}
    assert result["native_checks"] == "unavailable"
    assert stage


@pytest.mark.parametrize("has_pxr", [False, True])
def test_file_read_permission_error_is_not_missing_metadata(monkeypatch, tmp_path, has_pxr):
    path = binary_stub(tmp_path)
    monkeypatch.setattr(runtime, "_RUNTIME_INFO", runtime.RuntimeInfo(has_pxr=has_pxr))
    read_bytes = Path.read_bytes

    def deny_read(self):
        if self == path:
            raise PermissionError("permission denied by test")
        return read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", deny_read)
    result = runtime.validate_stage(str(path), strict=True)
    assert codes(result) == {"STAGE_OPEN_FAILED"}
    assert "permission denied" in result["issues"][0]["message"]
    assert result["native_checks"] == "unavailable"
