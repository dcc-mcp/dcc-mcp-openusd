from __future__ import annotations

import pytest

from dcc_mcp_openusd.runtime import detect_runtime

_HAS_PXR = detect_runtime().has_pxr


@pytest.mark.skipif(_HAS_PXR, reason="pxr is available — pxr-missing path cannot be tested")
class TestMaterialPxrMissing:
    """All material tools fail fast when pxr is not available."""

    def test_create_material_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, create_material

        stage = tmp_path / "scene.usda"
        stage.write_text("#usda 1.0\n", encoding="utf-8")
        with pytest.raises(OpenUsdError, match="pxr runtime"):
            create_material(str(stage), "/World/Mat")

    def test_create_preview_surface_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, create_preview_surface

        stage = tmp_path / "scene.usda"
        stage.write_text("#usda 1.0\n", encoding="utf-8")
        with pytest.raises(OpenUsdError, match="pxr runtime"):
            create_preview_surface(str(stage), "/World/Mat")

    def test_bind_material_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, bind_material

        stage = tmp_path / "scene.usda"
        stage.write_text("#usda 1.0\n", encoding="utf-8")
        with pytest.raises(OpenUsdError, match="pxr runtime"):
            bind_material(str(stage), "/World/Geo", "/World/Mat")


@pytest.mark.skipif(not _HAS_PXR, reason="pxr not available")
class TestMaterialPxrAvailable:
    """Material tools use the pxr runtime when present."""

    def test_create_material_creates_prim(self, tmp_path):
        from dcc_mcp_openusd.runtime import create_material, create_stage

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        result = create_material(stage_file, "/World/Mat")
        assert result["material_path"] == "/World/Mat"
        assert result["runtime"] == "pxr"

    def test_preview_surface_and_bind(self, tmp_path):
        from dcc_mcp_openusd.runtime import (
            bind_material,
            create_material,
            create_preview_surface,
            create_stage,
            define_xform,
        )

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        define_xform(stage_file, "/World/Geo")
        create_material(stage_file, "/World/Mat")
        shader_result = create_preview_surface(stage_file, "/World/Mat", diffuse_color=[0.8, 0.2, 0.2])
        assert shader_result["shader_path"] == "/World/Mat/Shader"
        assert shader_result["runtime"] == "pxr"

        bind_result = bind_material(stage_file, "/World/Geo", "/World/Mat")
        assert bind_result["prim_path"] == "/World/Geo"
        assert bind_result["runtime"] == "pxr"
