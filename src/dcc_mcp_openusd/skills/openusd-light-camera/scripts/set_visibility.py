"""Set authored visibility on an Imageable prim (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import set_visibility


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Visibility set", **set_visibility(**kwargs))


if __name__ == "__main__":
    run_main(main)
