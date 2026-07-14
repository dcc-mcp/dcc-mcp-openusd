"""Configure stage time codes (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import set_time_codes


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Time codes set", **set_time_codes(**kwargs))


if __name__ == "__main__":
    run_main(main)
