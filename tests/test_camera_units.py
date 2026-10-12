"""Camera's documented millimetres must survive scene unit changes."""

import pytest

pytest.importorskip("pxr")
from pxr import Usd, UsdGeom  # noqa: E402

from dcc_mcp_openusd.runtime import create_camera, create_stage  # noqa: E402


@pytest.mark.parametrize("meters_per_unit", [1.0, 0.01, 0.001])
def test_camera_focal_length_and_default_sensor_are_physical_millimeters(tmp_path, meters_per_unit):
    path = str(tmp_path / "camera.usda")
    create_stage(path, meters_per_unit=meters_per_unit)
    create_camera(path, "/World/Camera", focal_length=46, focus_distance=17, f_stop=4)
    stage = Usd.Stage.Open(path)
    camera = UsdGeom.Camera.Get(stage, "/World/Camera")
    usd_to_mm = 100 * UsdGeom.GetStageMetersPerUnit(stage)
    assert camera.GetFocalLengthAttr().Get() * usd_to_mm == pytest.approx(46)
    assert camera.GetHorizontalApertureAttr().Get() * usd_to_mm == pytest.approx(20.955)
    assert camera.GetVerticalApertureAttr().Get() * usd_to_mm == pytest.approx(15.2908)
    # Focus distance remains in scene units, and f-stop is dimensionless.
    assert camera.GetFocusDistanceAttr().Get() == 17
    assert camera.GetFStopAttr().Get() == 4


def test_camera_update_preserves_authored_sensor_apertures(tmp_path):
    path = str(tmp_path / "camera.usda")
    create_stage(path, meters_per_unit=1)
    stage = Usd.Stage.Open(path)
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateHorizontalApertureAttr().Set(0.36)
    camera.CreateVerticalApertureAttr().Set(0.24)
    stage.GetRootLayer().Save()
    create_camera(path, "/World/Camera", focal_length=35)
    stage.GetRootLayer().Reload()
    assert camera.GetFocalLengthAttr().Get() == pytest.approx(0.35)
    assert camera.GetHorizontalApertureAttr().Get() == pytest.approx(0.36)
    assert camera.GetVerticalApertureAttr().Get() == pytest.approx(0.24)
