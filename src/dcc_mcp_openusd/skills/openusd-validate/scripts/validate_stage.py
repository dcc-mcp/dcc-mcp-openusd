"""Validate an OpenUSD stage."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, validate_stage


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an OpenUSD stage.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    try:
        context = validate_stage(args.stage_file, args.strict)
        message = "OpenUSD stage is valid" if context["valid"] else "OpenUSD stage has validation issues"
        print(json.dumps({"success": True, "message": message, "context": context}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
