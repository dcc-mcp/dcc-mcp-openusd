"""Bind a UsdShadeMaterial to a prim (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, bind_material


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind a UsdShadeMaterial to a prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--material-path", required=True)
    args = parser.parse_args()

    try:
        result = bind_material(args.stage_file, args.prim_path, args.material_path)
        print(json.dumps({"success": True, "message": "Material bound", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
