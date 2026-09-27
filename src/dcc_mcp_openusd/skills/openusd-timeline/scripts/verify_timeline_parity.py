"""Assert that a stage and an OTIO timeline describe the same edit (pxr + opentimelineio required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_error, skill_success

from dcc_mcp_openusd.timeline import verify_timeline_parity


@skill_entry
def main(**kwargs) -> dict:
    result = verify_timeline_parity(**kwargs)
    if result["parity"]:
        return skill_success("Timeline parity verified", **result)

    summary = ", ".join(f"{item['field']}: {item['expected']} != {item['actual']}" for item in result["differences"])
    return skill_error(
        f"Timeline parity mismatch ({len(result['differences'])} field(s)): {summary}",
        "timeline_parity_mismatch",
        prompt="Re-run import_timeline with the reference timeline, then verify again.",
        **result,
    )


if __name__ == "__main__":
    run_main(main)
