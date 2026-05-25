"""Define an Xform prim."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, define_xform


def main() -> int:
    parser = argparse.ArgumentParser(description="Define an OpenUSD Xform prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    args = parser.parse_args()

    try:
        context = define_xform(args.stage_file, args.prim_path)
        print(json.dumps({"success": True, "message": f"Defined {args.prim_path}", "context": context}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
