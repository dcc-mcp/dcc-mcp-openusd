"""Modify stage-level metadata."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, set_stage_metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Modify stage metadata.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--up-axis", default=None)
    parser.add_argument("--meters-per-unit", type=float, default=None)
    parser.add_argument("--doc", default=None)
    parser.add_argument("--frames-per-second", type=float, default=None)
    args = parser.parse_args()

    try:
        context = set_stage_metadata(
            args.stage_file,
            up_axis=args.up_axis,
            meters_per_unit=args.meters_per_unit,
            doc=args.doc,
            frames_per_second=args.frames_per_second,
        )
        print(json.dumps({"success": True, "message": "Stage metadata updated", "context": context}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
