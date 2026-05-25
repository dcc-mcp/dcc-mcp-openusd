"""Snapshot an OpenUSD stage."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, snapshot_stage


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot an OpenUSD stage.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    try:
        context = snapshot_stage(args.stage_file, args.output_dir, args.name)
        print(json.dumps({"success": True, "message": "OpenUSD stage snapshot created", "context": context}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
