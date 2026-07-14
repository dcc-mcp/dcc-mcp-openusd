"""Create a variant set on a prim (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import add_variant_set


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Variant set created", **add_variant_set(**kwargs))


if __name__ == "__main__":
    run_main(main)
