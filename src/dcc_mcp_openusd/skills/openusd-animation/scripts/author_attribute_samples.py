"""Write attribute time samples on a prim (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import author_attribute_samples


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Attribute samples authored", **author_attribute_samples(**kwargs))


if __name__ == "__main__":
    run_main(main)
