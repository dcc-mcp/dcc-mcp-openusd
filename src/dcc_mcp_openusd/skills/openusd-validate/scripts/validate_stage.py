"""Validate an OpenUSD stage."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import validate_stage


@skill_entry
def main(**kwargs) -> dict:
    context = validate_stage(**kwargs)
    message = "OpenUSD stage is valid" if context["valid"] else "OpenUSD stage has validation issues"
    return skill_success(message, **context)


if __name__ == "__main__":
    run_main(main)
