"""Create a UsdShadeMaterial prim (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, create_material


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a UsdShadeMaterial prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    args = parser.parse_args()

    try:
        result = create_material(args.stage_file, args.prim_path)
        print(json.dumps({"success": True, "message": "Material created", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
