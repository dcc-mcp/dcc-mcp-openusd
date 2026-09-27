"""Apply an OpenTimelineIO timeline to a stage (pxr + opentimelineio required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.timeline import import_timeline


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Timeline imported", **import_timeline(**kwargs))


if __name__ == "__main__":
    run_main(main)
