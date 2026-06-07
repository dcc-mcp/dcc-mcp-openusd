"""Write xform time samples on a prim (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, author_xform_samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Author xform time samples.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--samples", required=True)
    args = parser.parse_args()

    try:
        samples = json.loads(args.samples)
    except json.JSONDecodeError as exc:
        print(json.dumps({"success": False, "message": f"Invalid samples JSON: {exc}"}))
        return 1

    try:
        result = author_xform_samples(args.stage_file, args.prim_path, samples)
        print(json.dumps({"success": True, "message": "Xform samples authored", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
