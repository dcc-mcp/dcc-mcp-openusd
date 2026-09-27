"""Export a stage's time axis as an OpenTimelineIO timeline (pxr + opentimelineio required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.timeline import export_timeline


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Timeline exported", **export_timeline(**kwargs))


if __name__ == "__main__":
    run_main(main)
