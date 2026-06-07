"""Set stage time range and frame rate (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, set_time_codes


def main() -> int:
    parser = argparse.ArgumentParser(description="Set stage time codes.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--start-time-code", type=float, default=1.0)
    parser.add_argument("--end-time-code", type=float, default=120.0)
    parser.add_argument("--frames-per-second", type=float, default=24.0)
    args = parser.parse_args()

    try:
        result = set_time_codes(
            args.stage_file,
            start_time_code=args.start_time_code,
            end_time_code=args.end_time_code,
            frames_per_second=args.frames_per_second,
        )
        print(json.dumps({"success": True, "message": "Time codes set", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
