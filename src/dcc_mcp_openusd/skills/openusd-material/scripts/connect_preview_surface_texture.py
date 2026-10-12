"""Connect a portable Preview Surface texture network (pxr-required)."""

from __future__ import annotations

from dcc_mcp_core.skill import run_main, skill_entry, skill_success

from dcc_mcp_openusd.runtime import connect_preview_surface_texture


@skill_entry
def main(**kwargs) -> dict:
    return skill_success("Preview Surface texture connected", **connect_preview_surface_texture(**kwargs))


if __name__ == "__main__":
    run_main(main)
