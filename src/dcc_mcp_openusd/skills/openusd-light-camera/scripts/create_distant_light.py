"""Create a USD distant light (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import create_distant_light


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Distant light created", **create_distant_light(**kwargs))


if __name__ == "__main__":
    run_main(main)
