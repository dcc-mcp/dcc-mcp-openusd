"""Add a sublayer to the stage root layer (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, add_sublayer


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a sublayer to the stage.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--sublayer-path", required=True)
    parser.add_argument("--position", type=int, default=None)
    args = parser.parse_args()

    try:
        result = add_sublayer(args.stage_file, args.sublayer_path, position=args.position)
        print(json.dumps({"success": True, "message": "Sublayer added", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
