"""Create a USD sphere light (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import create_sphere_light


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Sphere light created", **create_sphere_light(**kwargs))


if __name__ == "__main__":
    run_main(main)
