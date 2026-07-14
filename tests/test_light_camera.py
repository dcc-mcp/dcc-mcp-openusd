from __future__ import annotations

import pytest

from dcc_mcp_openusd.runtime import detect_runtime

_HAS_PXR = detect_runtime().has_pxr


@pytest.mark.skipif(_HAS_PXR, reason="pxr is available — pxr-missing path cannot be tested")
class TestLightCameraPxrMissing:
    """Light/camera tools fail fast when pxr is not available."""

    def _make_stage(self, tmp_path):
        stage = tmp_path / "scene.usda"
        stage.write_text("#usda 1.0\n", encoding="utf-8")
        return str(stage)

    def test_create_camera_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, create_camera

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            create_camera(self._make_stage(tmp_path), "/World/Camera")

    def test_create_distant_light_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, create_distant_light

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            create_distant_light(self._make_stage(tmp_path), "/World/Light")

    def test_create_sphere_light_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, create_sphere_light

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            create_sphere_light(self._make_stage(tmp_path), "/World/Light")

    def test_set_transform_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, set_transform

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            set_transform(self._make_stage(tmp_path), "/World/X", translate=[1, 0, 0])

    def test_set_visibility_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, set_visibility

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            set_visibility(self._make_stage(tmp_path), "/World/X", visible=False)


@pytest.mark.skipif(not _HAS_PXR, reason="pxr not available")
class TestLightCameraPxrAvailable:
    """Light/camera tools succeed when pxr is present."""

    def test_create_camera(self, tmp_path):
        from dcc_mcp_openusd.runtime import create_camera, create_stage

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        result = create_camera(stage_file, "/World/Camera", focal_length=35, f_stop=4)
        assert result["prim_path"] == "/World/Camera"
        assert result["runtime"] == "pxr"

    def test_create_lights_and_transform(self, tmp_path):
        from dcc_mcp_openusd.runtime import (
            create_camera,
            create_distant_light,
            create_dome_light,
            create_sphere_light,
            create_stage,
            set_transform,
        )

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        create_camera(stage_file, "/World/Camera")

        dl = create_distant_light(stage_file, "/World/KeyLight", color=[1, 0.9, 0.8])
        assert dl["runtime"] == "pxr"

        sl = create_sphere_light(stage_file, "/World/RimLight", color=[0.8, 0.9, 1])
        assert sl["runtime"] == "pxr"

        hdr = tmp_path / "studio.exr"
        hdr.touch()
        dome = create_dome_light(
            stage_file,
            "/World/Environment",
            texture_file=str(hdr),
            intensity=1.5,
            exposure=2.0,
            texture_format="latlong",
        )
        assert dome["texture_file"].endswith("studio.exr")

        from pxr import Usd, UsdLux

        stage = Usd.Stage.Open(stage_file)
        dome_light = UsdLux.DomeLight.Get(stage, "/World/Environment")
        assert dome_light.GetIntensityAttr().Get() == pytest.approx(1.5)
        assert dome_light.GetExposureAttr().Get() == pytest.approx(2.0)
        assert dome_light.GetTextureFileAttr().Get().path.endswith("studio.exr")
        assert dome_light.GetTextureFormatAttr().Get() == "latlong"

        xf = set_transform(stage_file, "/World/Camera", translate=[0, 2, 10], rotate=[-10, 0, 0])
        assert xf["runtime"] == "pxr"

    def test_set_visibility(self, tmp_path):
        from dcc_mcp_openusd.runtime import create_stage, define_xform, set_visibility

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        define_xform(stage_file, "/World/Atmosphere")

        hidden = set_visibility(stage_file, "/World/Atmosphere", visible=False)
        assert hidden["visibility"] == "invisible"

        from pxr import Usd, UsdGeom

        stage = Usd.Stage.Open(stage_file)
        prim = stage.GetPrimAtPath("/World/Atmosphere")
        assert UsdGeom.Imageable(prim).ComputeVisibility() == UsdGeom.Tokens.invisible

        shown = set_visibility(stage_file, "/World/Atmosphere", visible=True)
        assert shown["visibility"] == "inherited"
