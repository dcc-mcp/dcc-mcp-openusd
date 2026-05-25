"""Create a minimal OpenUSD stage."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, create_stage


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an OpenUSD stage.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--name", default="scene")
    parser.add_argument("--up-axis", default="Y")
    parser.add_argument("--meters-per-unit", type=float, default=1.0)
    args = parser.parse_args()

    try:
        context = create_stage(args.stage_file, args.name, args.up_axis, args.meters_per_unit)
        print(json.dumps({"success": True, "message": "OpenUSD stage created", "context": context}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
