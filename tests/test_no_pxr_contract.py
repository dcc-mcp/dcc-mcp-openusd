"""No-pxr contract tests: verify advanced tools raise cleanly when pxr is absent.

These tests FORCE has_pxr=False regardless of the current environment,
exercising the text-fallback path and verifying that "requires OpenUSD runtime"
is reported for pxr-only operations.
"""

from __future__ import annotations

import pytest

from dcc_mcp_openusd.runtime import (
    OpenUsdError,
    RuntimeInfo,
    create_stage,
    define_prim,
    require_pxr,
)


@pytest.fixture
def force_no_pxr(monkeypatch):
    """Force detect_runtime() to report has_pxr=False."""
    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=False))


def test_require_pxr_raises_clean_error(force_no_pxr):
    """require_pxr must raise OpenUsdError with actionable message."""
    with pytest.raises(OpenUsdError, match="requires the Pixar USD \\(pxr\\) package"):
        require_pxr("complex material authoring")


def test_advanced_tools_fallback_do_not_crash_but_flag_no_pxr(force_no_pxr, tmp_path):
    """Stage authoring without pxr must still produce valid USDA, not corrupt output."""
    stage_file = tmp_path / "scene.usda"
    result = create_stage(str(stage_file), name="contract_test")
    assert result["runtime"] == "text-fallback"

    # define_prim on Material type should succeed via text-fallback (no pxr required)
    result2 = define_prim(str(stage_file), "/World/TestMat", "Material")
    assert result2["runtime"] == "text-fallback"

    # Output must be valid USDA
    content = stage_file.read_text(encoding="utf-8")
    assert content.lstrip().startswith("#usda"), "Output must be USDA even in fallback mode"
    assert "Material" in content, "Material type must appear in fallback USDA"


def test_require_pxr_error_includes_feature_name(force_no_pxr):
    """Error message must mention the feature that triggered the guard."""
    with pytest.raises(OpenUsdError, match="material authoring"):
        require_pxr("complex material authoring")

    with pytest.raises(OpenUsdError, match="time samples"):
        require_pxr("time samples")
