"""Set xform operations on a prim."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, set_xform_ops


def main() -> int:
    parser = argparse.ArgumentParser(description="Set xform operations on a prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--translate", type=float, nargs=3, default=None)
    parser.add_argument("--rotate", type=float, nargs=3, default=None)
    parser.add_argument("--scale", type=float, nargs=3, default=None)
    args = parser.parse_args()

    try:
        context = set_xform_ops(
            args.stage_file,
            args.prim_path,
            translate=list(args.translate) if args.translate else None,
            rotate=list(args.rotate) if args.rotate else None,
            scale=list(args.scale) if args.scale else None,
        )
        print(json.dumps({"success": True, "message": f"Set xformOps on {args.prim_path}", "context": context}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
