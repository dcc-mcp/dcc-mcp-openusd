"""Tool entry-point regression coverage."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script(relative_path: str):
    path = Path(__file__).parents[1] / "src" / "dcc_mcp_openusd" / "skills" / relative_path
    spec = importlib.util.spec_from_file_location("openusd_test_tool", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_project_tool_accepts_schema_arguments(tmp_path: Path) -> None:
    tool = _load_script("openusd-project/scripts/create_project.py")

    result = tool.main(
        project_dir=str(tmp_path / "project"),
        name="MCP Project",
        up_axis="Y",
        meters_per_unit=1.0,
    )

    assert result["success"] is True
    assert (tmp_path / "project" / "scene.usda").is_file()


def test_all_tool_entry_points_return_result_envelopes() -> None:
    scripts = Path(__file__).parents[1] / "src" / "dcc_mcp_openusd" / "skills"

    for path in scripts.glob("*/scripts/*.py"):
        relative_path = path.relative_to(scripts).as_posix()
        tool = _load_script(relative_path)
        result = tool.main(__contract_probe__=True)
        assert isinstance(result, dict), relative_path
        assert result["success"] is False, relative_path
