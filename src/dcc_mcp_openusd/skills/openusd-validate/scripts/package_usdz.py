"""Package an OpenUSD stage as USDZ."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import package_usdz


@skill_entry
def main(**kwargs) -> dict:
    result = package_usdz(**kwargs)
    message = (
        "OpenUSD package created; dependencies resolved"
        if result["runtime"] == "pxr"
        else "Root-only ZIP created; native dependency checks unavailable"
    )
    return skill_success(message, **result)


if __name__ == "__main__":
    run_main(main)
