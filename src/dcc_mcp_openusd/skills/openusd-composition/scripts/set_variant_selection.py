"""Set the active variant selection in a variant set (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, set_variant_selection


def main() -> int:
    parser = argparse.ArgumentParser(description="Set variant selection on a prim.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--prim-path", required=True)
    parser.add_argument("--variant-set-name", required=True)
    parser.add_argument("--variant-name", required=True)
    args = parser.parse_args()

    try:
        result = set_variant_selection(
            args.stage_file, args.prim_path, args.variant_set_name, args.variant_name
        )
        print(json.dumps({"success": True, "message": "Variant selection set", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
