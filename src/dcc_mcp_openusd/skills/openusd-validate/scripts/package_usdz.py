"""Package an OpenUSD stage."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, package_usdz


def main() -> int:
    parser = argparse.ArgumentParser(description="Package an OpenUSD stage.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args()

    try:
        context = package_usdz(args.stage_file, args.output_file)
        print(json.dumps({"success": True, "message": "OpenUSD package created", "context": context}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
