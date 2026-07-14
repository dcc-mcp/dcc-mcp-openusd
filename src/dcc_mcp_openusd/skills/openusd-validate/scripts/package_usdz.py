"""Package an OpenUSD stage as USDZ."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import package_usdz


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("OpenUSD package created", **package_usdz(**kwargs))


if __name__ == "__main__":
    run_main(main)
