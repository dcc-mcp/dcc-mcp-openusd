"""Define a USD prim with an arbitrary type."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, define_prim


def main() -> int:
    parser = argparse.ArgumentParser(description="Define an OpenUSD prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--prim-type", default="Xform")
    args = parser.parse_args()

    try:
        context = define_prim(args.stage_file, args.prim_path, args.prim_type)
        print(
            json.dumps({"success": True, "message": f"Defined {args.prim_path} ({args.prim_type})", "context": context})
        )
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
