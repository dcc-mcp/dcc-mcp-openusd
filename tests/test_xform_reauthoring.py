"""Real USD editing must reuse the transform operations it already authored."""

import pytest

pytest.importorskip("pxr")
from pxr import Usd, UsdGeom  # noqa: E402

from dcc_mcp_openusd.runtime import (  # noqa: E402
    author_xform_samples,
    create_stage,
    define_xform,
    set_transform,
)


def make_stage(tmp_path):
    path = str(tmp_path / "scene.usda")
    create_stage(path)
    define_xform(path, "/World/CameraRig")
    return path


def test_set_transform_updates_existing_ops(tmp_path):
    path = make_stage(tmp_path)
    set_transform(path, "/World/CameraRig", translate=[1, 2, 3], rotate=[0, 10, 0], scale=[1, 1, 1])
    set_transform(path, "/World/CameraRig", translate=[4, 5, 6], rotate=[0, 20, 0])
    stage = Usd.Stage.Open(path)
    xf = UsdGeom.Xformable(stage.GetPrimAtPath("/World/CameraRig"))
    assert len(xf.GetOrderedXformOps()) == 3
    assert tuple(xf.GetTranslateOp().Get()) == (4, 5, 6)
    assert tuple(xf.GetRotateXYZOp().Get()) == (0, 20, 0)
    assert tuple(xf.GetScaleOp().Get()) == (1, 1, 1)


def test_animation_reuses_static_ops_and_can_be_edited_again(tmp_path):
    path = make_stage(tmp_path)
    set_transform(path, "/World/CameraRig", translate=[0, 0, 0])
    author_xform_samples(path, "/World/CameraRig", [{"time": 1, "translate": [1, 0, 0]}])
    author_xform_samples(
        path, "/World/CameraRig", [{"time": 1, "translate": [2, 0, 0]}, {"time": 24, "translate": [4, 0, 0]}]
    )
    stage = Usd.Stage.Open(path)
    xf = UsdGeom.Xformable(stage.GetPrimAtPath("/World/CameraRig"))
    assert len(xf.GetOrderedXformOps()) == 3
    assert xf.GetTranslateOp().GetTimeSamples() == [1, 24]
    assert tuple(xf.GetTranslateOp().Get(1)) == (2, 0, 0)
    assert tuple(xf.GetTranslateOp().Get(24)) == (4, 0, 0)


def test_animation_can_override_inherited_ops_without_editing_source(tmp_path):
    source = make_stage(tmp_path)
    author_xform_samples(source, "/World/CameraRig", [{"time": 1, "translate": [1, 0, 0]}])
    source_bytes = (tmp_path / "scene.usda").read_bytes()
    path = str(tmp_path / "shot.usda")
    stage = Usd.Stage.CreateNew(path)
    stage.GetRootLayer().subLayerPaths = ["scene.usda"]
    stage.GetRootLayer().Save()
    author_xform_samples(
        path, "/World/CameraRig", [{"time": 1, "translate": [3, 0, 0]}, {"time": 48, "translate": [6, 0, 0]}]
    )
    stage.GetRootLayer().Reload()
    xf = UsdGeom.Xformable(stage.GetPrimAtPath("/World/CameraRig"))
    assert len(xf.GetOrderedXformOps()) == 3
    assert tuple(xf.GetTranslateOp().Get(48)) == (6, 0, 0)
    assert (tmp_path / "scene.usda").read_bytes() == source_bytes


def test_inactive_existing_op_is_reinserted_without_losing_reset_stack(tmp_path):
    path = make_stage(tmp_path)
    stage = Usd.Stage.Open(path)
    xf = UsdGeom.Xformable(stage.GetPrimAtPath("/World/CameraRig"))
    xf.AddTranslateOp(UsdGeom.XformOp.PrecisionFloat).Set((1, 2, 3))
    xf.SetXformOpOrder([], resetXformStack=True)
    stage.GetRootLayer().Save()
    set_transform(path, "/World/CameraRig", translate=[4, 5, 6])
    stage.GetRootLayer().Reload()
    assert xf.GetResetXformStack()
    assert len(xf.GetOrderedXformOps()) == 1
    assert xf.GetTranslateOp().GetPrecision() == UsdGeom.XformOp.PrecisionFloat
    assert tuple(xf.GetLocalTransformation().ExtractTranslation()) == (4, 5, 6)
