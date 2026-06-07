"""Create a UsdGeomCamera prim (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, create_camera


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a UsdGeomCamera prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--focal-length", type=float, default=50.0)
    parser.add_argument("--focus-distance", type=float, default=100.0)
    parser.add_argument("--f-stop", type=float, default=2.8)
    args = parser.parse_args()

    try:
        result = create_camera(
            args.stage_file, args.prim_path,
            focal_length=args.focal_length,
            focus_distance=args.focus_distance,
            f_stop=args.f_stop,
        )
        print(json.dumps({"success": True, "message": "Camera created", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
