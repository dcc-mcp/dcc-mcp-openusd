"""Update OpenUSD stage metadata."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import set_stage_metadata


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Stage metadata updated", **set_stage_metadata(**kwargs))


if __name__ == "__main__":
    run_main(main)
