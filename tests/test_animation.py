from __future__ import annotations

import pytest

from dcc_mcp_openusd.runtime import detect_runtime

_HAS_PXR = detect_runtime().has_pxr


@pytest.mark.skipif(_HAS_PXR, reason="pxr is available — pxr-missing path cannot be tested")
class TestAnimationPxrMissing:
    """Animation tools fail fast when pxr is not available."""

    def _make_stage(self, tmp_path):
        stage = tmp_path / "scene.usda"
        stage.write_text("#usda 1.0\n", encoding="utf-8")
        return str(stage)

    def test_set_time_codes_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, set_time_codes

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            set_time_codes(self._make_stage(tmp_path))

    def test_author_xform_samples_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, author_xform_samples

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            author_xform_samples(self._make_stage(tmp_path), "/World/X", [{"time": 1, "rotate": [0, 0, 0]}])

    def test_author_attribute_samples_fails_without_pxr(self, tmp_path):
        from dcc_mcp_openusd.runtime import OpenUsdError, author_attribute_samples

        with pytest.raises(OpenUsdError, match="pxr runtime"):
            author_attribute_samples(
                self._make_stage(tmp_path), "/World/X", "myFloat", [{"time": 1, "value": 0.5}]
            )


@pytest.mark.skipif(not _HAS_PXR, reason="pxr not available")
class TestAnimationPxrAvailable:
    """Animation tools succeed when pxr is present."""

    def test_set_time_codes(self, tmp_path):
        from dcc_mcp_openusd.runtime import create_stage, set_time_codes

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        result = set_time_codes(stage_file, start_time_code=1, end_time_code=120, frames_per_second=24)
        assert result["start_time_code"] == 1
        assert result["end_time_code"] == 120
        assert result["runtime"] == "pxr"

    def test_author_xform_samples_writes_keyframes(self, tmp_path):
        from dcc_mcp_openusd.runtime import author_xform_samples, create_stage, define_xform

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        define_xform(stage_file, "/World/Asset")
        samples = [
            {"time": 1, "rotate": [0, 0, 0], "scale": [1, 1, 1]},
            {"time": 60, "rotate": [0, 180, 0], "scale": [1, 1, 1]},
            {"time": 120, "rotate": [0, 360, 0], "scale": [1, 1, 1]},
        ]
        result = author_xform_samples(stage_file, "/World/Asset", samples)
        assert result["sample_count"] == 3
        assert result["runtime"] == "pxr"

    def test_author_attribute_samples_writes_samples(self, tmp_path):
        from dcc_mcp_openusd.runtime import author_attribute_samples, create_stage, define_xform

        stage_file = str(tmp_path / "scene.usda")
        create_stage(stage_file)
        define_xform(stage_file, "/World/Asset")
        samples = [{"time": 1, "value": 0.5}, {"time": 60, "value": 1.0}]
        result = author_attribute_samples(stage_file, "/World/Asset", "dccMcp:slider", samples)
        assert result["sample_count"] == 2
        assert result["runtime"] == "pxr"
