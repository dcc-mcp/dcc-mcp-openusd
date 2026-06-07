"""Create a SphereLight prim (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, create_sphere_light


def _parse_float_list(raw: str | None):
    if raw is None:
        return None
    return [float(v) for v in raw.split(",")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a SphereLight prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--radius", type=float, default=1.0)
    parser.add_argument("--intensity", type=float, default=1.0)
    parser.add_argument("--color", default=None)
    args = parser.parse_args()

    try:
        result = create_sphere_light(
            args.stage_file, args.prim_path,
            radius=args.radius,
            intensity=args.intensity,
            color=_parse_float_list(args.color),
        )
        print(json.dumps({"success": True, "message": "Sphere light created", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
