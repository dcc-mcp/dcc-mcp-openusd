"""Create a UsdPreviewSurface shader (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import create_preview_surface


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Preview surface created", **create_preview_surface(**kwargs))


if __name__ == "__main__":
    run_main(main)
