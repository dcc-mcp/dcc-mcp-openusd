"""Set translate/rotate/scale on an Xformable prim (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_error, skill_success

from dcc_mcp_openusd.runtime import set_transform


@skill_entry
def main(**kwargs) -> dict:
    if not any(kwargs.get(name) is not None for name in ("translate", "rotate", "scale")):
        return skill_error("At least one of translate, rotate, scale is required")
    return skill_success("Transform set", **set_transform(**kwargs))


if __name__ == "__main__":
    run_main(main)
