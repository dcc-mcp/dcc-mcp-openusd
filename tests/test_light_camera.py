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

        xf = set_transform(stage_file, "/World/Camera", translate=[0, 2, 10], rotate=[-10, 0, 0])
        assert xf["runtime"] == "pxr"
