"""Set translate/rotate/scale on an Xformable prim (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, set_transform


def _parse_float_list(raw: str | None):
    if raw is None:
        return None
    return [float(v) for v in raw.split(",")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Set transform on a prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--translate", default=None)
    parser.add_argument("--rotate", default=None)
    parser.add_argument("--scale", default=None)
    args = parser.parse_args()

    if not any([args.translate, args.rotate, args.scale]):
        print(json.dumps({"success": False, "message": "At least one of translate, rotate, scale is required"}))
        return 1

    try:
        result = set_transform(
            args.stage_file, args.prim_path,
            translate=_parse_float_list(args.translate),
            rotate=_parse_float_list(args.rotate),
            scale=_parse_float_list(args.scale),
        )
        print(json.dumps({"success": True, "message": "Transform set", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
