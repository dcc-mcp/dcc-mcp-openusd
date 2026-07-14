"""Create a self-contained OpenUSD project folder."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import create_project


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("OpenUSD project created", **create_project(**kwargs))


if __name__ == "__main__":
    run_main(main)
