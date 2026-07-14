"""List an OpenUSD stage."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import list_stage


@skill_entry
def main(**kwargs) -> dict:
    context = list_stage(**kwargs)
    return skill_success(f"OpenUSD stage has {context['prim_count']} prims", **context)


if __name__ == "__main__":
    run_main(main)
