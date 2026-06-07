"""Create a variant set on a prim (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, add_variant_set


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a variant set on a prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--variant-set-name", required=True)
    args = parser.parse_args()

    try:
        result = add_variant_set(args.stage_file, args.prim_path, args.variant_set_name)
        print(json.dumps({"success": True, "message": "Variant set created", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
