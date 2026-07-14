"""Create a portable UsdGeom.Points FX primitive."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import create_points


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("USD points created", **create_points(**kwargs))


if __name__ == "__main__":
    run_main(main)
