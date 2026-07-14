"""Bind a material to a prim (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import bind_material


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Material bound", **bind_material(**kwargs))


if __name__ == "__main__":
    run_main(main)
