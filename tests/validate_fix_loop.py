"""Shared primitives for driving the validate -> fix -> re-validate loop.

The helpers here deliberately go through the *shipped skill entry points* rather
than the underlying ``runtime`` functions, because the loop under test is the
one an agent follows: read ``suggested_fix`` off a validation issue, dispatch
the skill it names, re-validate. Dispatching by advertised name also means a
renamed or relocated tool fails the loop test instead of being papered over by
a path the test happens to know.

Nothing here requires a host USD service or a network asset library.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List

import yaml

from dcc_mcp_openusd.runtime import _FIX_SKILL_BY_CODE

SKILLS_DIR = Path(__file__).parents[1] / "src" / "dcc_mcp_openusd" / "skills"
DATA_DIR = Path(__file__).parent / "data" / "usd"

BROKEN_REFERENCE = DATA_DIR / "broken_reference.usda"
UNBOUND_MATERIAL = DATA_DIR / "unbound_material.usda"

#: Minimal replacement asset for the broken reference. The fix needs a file
#: that exists on disk; this one is self-contained and portable.
ASSET_TEMPLATE = (
    '#usda 1.0\n(\n    defaultPrim = "Prop"\n    metersPerUnit = 1\n    upAxis = "Y"\n)\n\ndef Mesh "Prop"\n{\n}\n'
)


def _skill_index() -> Dict[str, Path]:
    """Map every ``skill__tool`` name to its shipped entry-point script.

    Built from the ``SKILL.md`` name and each skill's ``tools.yaml`` catalog,
    which is what the runtime consumes. A tool that is renamed, or whose
    ``source_file`` moves, drops out of this index and the loop test fails.
    """
    index: Dict[str, Path] = {}
    for skill_dir in sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir()):
        tools_file = skill_dir / "tools.yaml"
        skill_md = skill_dir / "SKILL.md"
        if not tools_file.is_file() or not skill_md.is_file():
            continue
        front_matter = skill_md.read_text(encoding="utf-8").split("---")[1]
        skill_name = yaml.safe_load(front_matter)["name"].replace("-", "_")
        catalog = yaml.safe_load(tools_file.read_text(encoding="utf-8"))
        for tool in catalog["tools"]:
            index[f"{skill_name}__{tool['name']}"] = skill_dir / tool["source_file"]
    return index


SKILL_INDEX = _skill_index()


def call_skill(skill: str, **kwargs: Any) -> Dict[str, Any]:
    """Invoke a skill entry point by its advertised ``skill__tool`` name."""
    script = SKILL_INDEX.get(skill)
    assert script, f"skill '{skill}' is not declared in the bundled tools.yaml catalog"
    spec = importlib.util.spec_from_file_location(f"openusd_loop_{skill}", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main(**kwargs)


def validate(stage_file: Path) -> Dict[str, Any]:
    """Run the validate tool and return its agent-facing envelope."""
    return call_skill("openusd_validate__validate_stage", stage_file=str(stage_file))


def issues(envelope: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the issue list an agent reads out of a validate envelope."""
    return envelope["context"]["issues"]


def code_count(envelope: Dict[str, Any], code: str) -> int:
    """Count how many issues carry *code*."""
    return sum(1 for issue in issues(envelope) if issue["code"] == code)


def issue_for_code(envelope: Dict[str, Any], code: str) -> Dict[str, Any]:
    """Return the single issue carrying *code*, failing loudly when ambiguous."""
    matches = [issue for issue in issues(envelope) if issue["code"] == code]
    assert len(matches) == 1, f"expected exactly one {code} issue, got {len(matches)}"
    return matches[0]


def dispatch_suggested_fix(issue: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    """Apply the fix an issue advertises, without the caller choosing the skill.

    The skill name and its arguments both come from ``suggested_fix``; *extra*
    only supplies values the validator cannot know (an asset library, an apply
    flag). Picking the skill here would stop this being a loop test.
    """
    suggested = issue["suggested_fix"]
    assert suggested, "the issue must advertise a machine-usable fix"
    assert suggested["skill"] == _FIX_SKILL_BY_CODE[issue["code"]]
    assert suggested["args"]["stage_file"], "the fix must name the stage to act on"
    return call_skill(suggested["skill"], **suggested["args"], **extra)
