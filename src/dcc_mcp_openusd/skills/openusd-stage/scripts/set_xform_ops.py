"""Set transform operations on an OpenUSD prim."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import set_xform_ops


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Xform operations set", **set_xform_ops(**kwargs))


if __name__ == "__main__":
    run_main(main)
