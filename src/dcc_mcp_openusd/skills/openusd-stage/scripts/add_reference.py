"""Add an OpenUSD reference arc."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, add_reference


def main() -> int:
    parser = argparse.ArgumentParser(description="Add an OpenUSD reference.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--asset-path", required=True)
    parser.add_argument("--prim-type", default="Xform")
    args = parser.parse_args()

    try:
        context = add_reference(args.stage_file, args.prim_path, args.asset_path, args.prim_type)
        print(json.dumps({"success": True, "message": f"Referenced {args.asset_path}", "context": context}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
