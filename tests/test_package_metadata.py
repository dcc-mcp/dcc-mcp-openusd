from __future__ import annotations

import json
import re
from pathlib import Path

import dcc_mcp_openusd

ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_is_synchronized():
    manifest = json.loads(ROOT.joinpath(".release-please-manifest.json").read_text(encoding="utf-8"))
    pyproject = ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8")
    pyproject_version = re.search(r'(?m)^version = "([^"]+)"$', pyproject)

    assert re.fullmatch(r"\d+\.\d+\.\d+", dcc_mcp_openusd.__version__)
    assert pyproject_version is not None
    assert pyproject_version.group(1) == dcc_mcp_openusd.__version__
    assert manifest["."] == dcc_mcp_openusd.__version__


def test_bundled_skill_files_exist():
    skills_dir = ROOT / "src" / "dcc_mcp_openusd" / "skills"
    for name in ["openusd-project", "openusd-stage", "openusd-validate"]:
        assert skills_dir.joinpath(name, "SKILL.md").exists()
        assert skills_dir.joinpath(name, "tools.yaml").exists()


def test_public_api_exports_server():
    assert dcc_mcp_openusd.SERVER_NAME == "dcc-mcp-openusd"
    assert dcc_mcp_openusd.DEFAULT_PORT == 8765
    assert callable(dcc_mcp_openusd.start_server)
