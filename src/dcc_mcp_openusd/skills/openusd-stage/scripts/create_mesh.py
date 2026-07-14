"""Create portable renderer-neutral UsdGeom.Mesh topology."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import create_mesh


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("USD mesh created", **create_mesh(**kwargs))


if __name__ == "__main__":
    run_main(main)
