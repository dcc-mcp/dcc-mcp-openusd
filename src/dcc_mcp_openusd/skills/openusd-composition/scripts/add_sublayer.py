"""Add a sublayer to a stage (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import add_sublayer


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Sublayer added", **add_sublayer(**kwargs))


if __name__ == "__main__":
    run_main(main)
