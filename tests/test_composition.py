from __future__ import annotations

import pytest

from dcc_mcp_openusd.runtime import detect_runtime

_HAS_PXR = detect_runtime().has_pxr


@pytest.mark.skipif(_HAS_PXR, reason="pxr is available — pxr-missing path cannot be tested")
class TestCompositionPxrMissing:
    """Composition tools fail fast when pxr is not available."""

    def _make_stage(self, tmp_path):
        stage = tmp_path / "scene.usda"
        stage.write_text("#usda 1.0\n", encoding="utf-8")
        return str(stage)

    def test_add_sublayer_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, add_sublayer

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            add_sublayer(self._make_stage(tmp_path), "props.usda")

    def test_add_payload_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, add_payload

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            add_payload(self._make_stage(tmp_path), "/World/Payload", "asset.usda")

    def test_add_variant_set_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, add_variant_set

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            add_variant_set(self._make_stage(tmp_path), "/World/X", "lod")

    def test_set_variant_selection_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, set_variant_selection

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            set_variant_selection(self._make_stage(tmp_path), "/World/X", "lod", "high")


@pytest.mark.skipif(not _HAS_PXR, reason="pxr not available")
class TestCompositionPxrAvailable:
    """Composition tools succeed when pxr is present."""

    def test_add_sublayer(self, tmp_path):
        from dcc_mcp_openusd.runtime import add_sublayer, create_stage

        stage_file = str(tmp_path / "scene.usda")
        sub = tmp_path / "props.usda"
        sub.write_text("#usda 1.0\n", encoding="utf-8")
        create_stage(stage_file)
        result = add_sublayer(stage_file, str(sub))
        assert "props.usda" in result["sublayer_path"]
        assert result["runtime"] == "pxr"

    def test_add_payload(self, tmp_path):
        from dcc_mcp_openusd.runtime import add_payload, create_stage

        stage_file = str(tmp_path / "scene.usda")
        asset = tmp_path / "asset.usda"
        asset.write_text("#usda 1.0\n", encoding="utf-8")
        create_stage(stage_file)
        result = add_payload(stage_file, "/World/Payload", str(asset))
        assert result["prim_path"] == "/World/Payload"
        assert result["runtime"] == "pxr"

    def test_variant_set_and_selection(self, tmp_path):
        from dcc_mcp_openusd.runtime import (
            add_variant_set,
            create_stage,
            define_xform,
            set_variant_selection,
        )

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        define_xform(stage_file, "/World/Hero")
        vs = add_variant_set(stage_file, "/World/Hero", "lod")
        assert vs["variant_set_name"] == "lod"
        assert vs["runtime"] == "pxr"

        sel = set_variant_selection(stage_file, "/World/Hero", "lod", "high")
        assert sel["variant_name"] == "high"
        assert sel["runtime"] == "pxr"
