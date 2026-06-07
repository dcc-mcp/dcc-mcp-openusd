"""Create a UsdPreviewSurface shader and connect it to a material (pxr-required)."""

from __future__ import annotations

import argparse
import json
import sys

from dcc_mcp_openusd.runtime import OpenUsdError, create_preview_surface


def _parse_float_list(raw: str | None):
    if raw is None:
        return None
    return [float(v) for v in raw.split(",")]


def _parse_optional_str(raw: str | None) -> str | None:
    return raw if raw else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a UsdPreviewSurface shader.")
    parser.add_argument("--stage-file", required=True)
    parser.add_argument("--material-path", required=True)
    parser.add_argument("--shader-path", default=None)
    parser.add_argument("--diffuse-color", default=None)
    args = parser.parse_args()

    try:
        result = create_preview_surface(
            args.stage_file,
            args.material_path,
            shader_path=_parse_optional_str(args.shader_path),
            diffuse_color=_parse_float_list(args.diffuse_color),
        )
        print(json.dumps({"success": True, "message": "Preview surface created", **result}))
        return 0
    except OpenUsdError as exc:
        print(json.dumps({"success": False, "message": str(exc), "runtime": "none"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
