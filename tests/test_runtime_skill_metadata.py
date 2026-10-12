"""The real Core parser must retain every bundled typed tool contract."""

import json
from pathlib import Path

import pytest
import yaml
from dcc_mcp_core import parse_skill_md

SKILLS = Path(__file__).parents[1] / "src" / "dcc_mcp_openusd" / "skills"


@pytest.mark.parametrize("skill_dir", sorted(SKILLS.glob("openusd-*")), ids=lambda path: path.name)
def test_core_parser_retains_bundled_tools_and_schemas(skill_dir):
    declared = yaml.safe_load((skill_dir / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    metadata = parse_skill_md(str(skill_dir))
    assert metadata is not None
    parsed = {tool.name: tool for tool in metadata.tools}
    assert set(parsed) == {tool["name"] for tool in declared}
    for tool in declared:
        assert json.loads(parsed[tool["name"]].input_schema) == tool["input_schema"]
