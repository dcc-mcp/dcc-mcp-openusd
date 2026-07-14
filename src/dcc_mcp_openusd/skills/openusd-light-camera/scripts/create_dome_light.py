"""Create a USD dome light with an optional HDR texture."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import create_dome_light


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Dome light created", **create_dome_light(**kwargs))


if __name__ == "__main__":
    run_main(main)
