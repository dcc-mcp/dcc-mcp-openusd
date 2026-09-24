"""Validate an OpenUSD stage."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry

from dcc_mcp_openusd.runtime import validate_stage
from dcc_mcp_openusd.validation import ValidationResult, to_tool_result_envelope


@skill_entry
def main(**kwargs) -> dict:
    result = ValidationResult.from_value(validate_stage(**kwargs))
    return to_tool_result_envelope(result).to_dict(prune_empty=False)


if __name__ == "__main__":
    run_main(main)
