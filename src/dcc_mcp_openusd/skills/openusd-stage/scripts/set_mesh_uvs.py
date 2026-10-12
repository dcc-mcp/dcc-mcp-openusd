"""Author mesh texture coordinates (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import set_mesh_uvs


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Mesh UVs authored", **set_mesh_uvs(**kwargs))


if __name__ == "__main__":
    run_main(main)
