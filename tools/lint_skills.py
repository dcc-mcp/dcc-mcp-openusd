"""Validate bundled DCC-MCP skill metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate bundled skills.")
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args()

    skills_dir = Path(__file__).resolve().parents[1] / "src" / "dcc_mcp_openusd" / "skills"
    skill_dirs = sorted(path for path in skills_dir.iterdir() if path.is_dir())
    failures = []
    warnings = []
    try:
        from dcc_mcp_core import validate_skill
    except Exception as exc:
        failures.append(f"dcc_mcp_core.validate_skill unavailable: {exc}")
        validate_skill = None

    for skill_dir in skill_dirs:
        if validate_skill is None:
            continue
        report = validate_skill(str(skill_dir))
        is_valid = bool(getattr(report, "is_valid", False))
        report_errors = list(getattr(report, "errors", []) or [])
        report_warnings = list(getattr(report, "warnings", []) or [])
        if not is_valid:
            failures.extend(f"{skill_dir.name}: {item}" for item in report_errors)
        warnings.extend(f"{skill_dir.name}: {item}" for item in report_warnings)

    for warning in warnings:
        print(f"warning: {warning}")
    for failure in failures:
        print(f"error: {failure}", file=sys.stderr)

    if failures or (warnings and args.warnings_as_errors):
        return 1
    print(f"validated {len(skill_dirs)} bundled skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
