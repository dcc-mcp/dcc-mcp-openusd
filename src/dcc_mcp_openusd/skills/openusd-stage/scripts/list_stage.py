"""List an OpenUSD stage."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, list_stage


def main() -> int:
    parser = argparse.ArgumentParser(description="List an OpenUSD stage.")
    parser.add_argument("--stage-file", required=True)
    args = parser.parse_args()

    try:
        context = list_stage(args.stage_file)
        print(
            json.dumps(
                {"success": True, "message": f"OpenUSD stage has {context['prim_count']} prims", "context": context}
            )
        )
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
