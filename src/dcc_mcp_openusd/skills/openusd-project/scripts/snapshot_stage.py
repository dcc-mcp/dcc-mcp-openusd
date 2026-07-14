"""Create a deterministic snapshot of an OpenUSD stage."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import snapshot_stage


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("OpenUSD stage snapshot created", **snapshot_stage(**kwargs))


if __name__ == "__main__":
    run_main(main)
