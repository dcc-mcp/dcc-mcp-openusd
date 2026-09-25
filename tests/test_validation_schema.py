"""The frozen ``ValidationIssue`` / ``ValidationResult`` schema.

These tests pin the schema itself, not the rules that produce it. Every rule is
covered by parameterizing over :data:`~dcc_mcp_openusd.runtime.VALIDATION_RULES`
so a newly registered code cannot ship without guidance, severity and a
non-empty ``next_steps``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dcc_mcp_openusd.runtime import (
    _FIX_SKILL_BY_CODE,
    _GUIDANCE_BY_CODE,
    _RULE_SEVERITY,
    _STRICT_ERROR_RULES,
    VALIDATION_RULES,
    _next_steps_for,
    validate_stage,
)
from dcc_mcp_openusd.validation import (
    SEVERITIES,
    VALIDATION_FAILED,
    ValidationIssue,
    ValidationLocation,
    ValidationResult,
    aggregate_next_steps,
    format_summary_message,
    layer_location,
    line_location,
    prim_location,
    summarize_issues,
    to_tool_result_envelope,
)

DATA_DIR = Path(__file__).parent / "data" / "usd"
BROKEN_REFERENCE = DATA_DIR / "broken_reference.usda"
UNBOUND_MATERIAL = DATA_DIR / "unbound_material.usda"
UNIT_MISMATCH = DATA_DIR / "unit_mismatch.usda"

ALL_CODES = sorted(VALIDATION_RULES)


# ── rule registry: the three tables must stay in lockstep ──────────────────


def test_rule_tables_share_the_same_key_set():
    """A new code must be registered in all three tables at once.

    Adding a rule to :data:`VALIDATION_RULES` alone would leave the validator
    raising ``KeyError`` at runtime, so the key sets are pinned equal here.
    """
    assert set(VALIDATION_RULES) == set(_RULE_SEVERITY)
    assert set(VALIDATION_RULES) == set(_GUIDANCE_BY_CODE)


def test_severities_and_guidance_are_well_formed():
    """Every severity is a schema severity and every guidance string is usable."""
    for code in ALL_CODES:
        assert _RULE_SEVERITY[code] in SEVERITIES, code
        assert _GUIDANCE_BY_CODE[code].strip(), code


def test_fix_skills_only_cover_registered_rules():
    """A fix skill may only be wired to a code the validator can emit."""
    assert set(_FIX_SKILL_BY_CODE) <= set(VALIDATION_RULES)
    assert _STRICT_ERROR_RULES <= set(VALIDATION_RULES)


def test_strict_rules_are_promotable():
    """Only non-error rules can be promoted, or ``strict_promoted`` is a lie."""
    for code in _STRICT_ERROR_RULES:
        assert _RULE_SEVERITY[code] != "error", code


@pytest.mark.parametrize("code", ALL_CODES)
def test_every_rule_yields_non_empty_next_steps(code):
    """No rule may leave an agent without a next move.

    Parameterized over the registry so a rule added later is covered
    automatically instead of relying on the author to add a test.
    """
    suggested_fix, next_steps = _next_steps_for(code)

    assert next_steps, f"{code} produced no next_steps"
    for step in next_steps:
        assert step["action"], f"{code} produced a step without an action"
    # Without a stage path a fix-skill rule has no args to build, so it falls
    # back to guidance; either way the list stays non-empty.
    assert suggested_fix is None or suggested_fix["skill"] == _FIX_SKILL_BY_CODE[code]


@pytest.mark.parametrize("code", ALL_CODES)
def test_every_rule_with_a_fix_skill_builds_a_suggested_fix(code):
    """Given a stage path, a fix-skill rule offers a machine-readable fix."""
    _, next_steps = _next_steps_for(code, stage_file="/work/shot.usda", prim_path="/Root/Mesh")

    assert next_steps
    if code in _FIX_SKILL_BY_CODE:
        assert next_steps[0]["action"] == _FIX_SKILL_BY_CODE[code]
        assert next_steps[0]["args"]["stage_file"] == "/work/shot.usda"
    else:
        assert next_steps[0]["action"] == "manual_fix"
        assert next_steps[0]["detail"] == _GUIDANCE_BY_CODE[code]


# ── location: a discriminated object, not an overloaded string ─────────────


def test_prim_location():
    location = prim_location("/Root/Mesh")
    assert location.to_dict() == {
        "kind": "prim",
        "path": "/Root/Mesh",
        "line": None,
        "label": "/Root/Mesh",
    }


def test_layer_location():
    location = layer_location("stage.usda")
    assert location.to_dict() == {
        "kind": "layer",
        "path": "stage.usda",
        "line": None,
        "label": "[stage.usda]",
    }


def test_line_location():
    location = line_location(1)
    assert location.to_dict() == {
        "kind": "line",
        "path": None,
        "line": 1,
        "label": "[line 1]",
    }


def test_label_reproduces_the_legacy_string():
    """``label`` is what the old single-string field carried, verbatim."""
    assert prim_location("/World/Prop").legacy_value == "/World/Prop"
    assert layer_location("sub.usda").legacy_value == "[sub.usda]"
    assert line_location(7).legacy_value == "[line 7]"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/Root/Mesh", ("prim", "/Root/Mesh", None)),
        ("[stage.usda]", ("layer", "stage.usda", None)),
        ("[line 1]", ("line", None, 1)),
    ],
)
def test_legacy_strings_still_parse(text, expected):
    """One migration window: readers accept the old string form."""
    location = ValidationLocation.from_value(text, warn=False)
    assert (location.kind, location.path, location.line) == expected
    assert location.label == text


def test_legacy_strings_warn():
    """The legacy read path is deprecated, and says so."""
    with pytest.warns(DeprecationWarning, match="legacy validation 'location'"):
        ValidationLocation.from_value("[stage.usda]")


def test_invalid_locations_are_rejected():
    """A location that mixes address spaces cannot be built."""
    with pytest.raises(ValueError, match="unknown location kind"):
        ValidationLocation(kind="vertex", path="/Root")
    with pytest.raises(ValueError, match="requires a non-empty path"):
        prim_location("")
    with pytest.raises(ValueError, match="must not carry a path"):
        ValidationLocation(kind="line", path="/Root", line=1)
    with pytest.raises(ValueError, match="positive integer line number"):
        line_location(0)
    with pytest.raises(ValueError, match="must not carry a line number"):
        ValidationLocation(kind="prim", path="/Root", line=3)


def test_every_emitted_issue_carries_a_discriminated_location():
    """Acceptance: ``_run_validators`` output always has ``kind`` + payload."""
    for sample in (BROKEN_REFERENCE, UNBOUND_MATERIAL, UNIT_MISMATCH):
        result = validate_stage(str(sample))
        assert result["issues"], sample.name
        for issue in result["issues"]:
            location = issue["location"]
            assert set(location) == {"kind", "path", "line", "label"}
            assert location["kind"] in {"prim", "layer", "line"}
            if location["kind"] == "line":
                assert isinstance(location["line"], int) and location["path"] is None
            else:
                assert location["path"] and location["line"] is None
            assert location["label"]


# ── issue ──────────────────────────────────────────────────────────────────


def test_issue_round_trips_through_the_schema():
    issue = ValidationIssue(
        code="UNRESOLVED_REFERENCE",
        severity="error",
        message="Reference cannot be resolved",
        location=prim_location("/Root/Mesh"),
        suggested_fix={"skill": "openusd_stage__fix_reference_path", "args": {"stage_file": "shot.usda"}},
        next_steps=[{"action": "openusd_stage__fix_reference_path", "args": {"stage_file": "shot.usda"}}],
    )

    payload = issue.to_dict()
    assert set(payload) == {
        "code",
        "severity",
        "message",
        "location",
        "strict_promoted",
        "suggested_fix",
        "next_steps",
    }
    assert payload["location"]["kind"] == "prim"
    assert payload["strict_promoted"] is False

    restored = ValidationIssue.from_value(payload)
    assert restored.to_dict() == payload
    # The object form gives callers a typed location without re-parsing.
    assert restored.location == prim_location("/Root/Mesh")
    assert restored.location.path == "/Root/Mesh"


def test_issue_rejects_unknown_severity_and_empty_message():
    with pytest.raises(ValueError, match="unknown severity"):
        ValidationIssue(code="X", severity="fatal", message="m", location=prim_location("/"))
    with pytest.raises(ValueError, match="non-empty message"):
        ValidationIssue(code="X", severity="error", message="", location=prim_location("/"))


def test_issue_accepts_a_legacy_location_string():
    with pytest.warns(DeprecationWarning):
        issue = ValidationIssue.from_value(
            {
                "code": "MISSING_UP_AXIS",
                "severity": "warning",
                "message": "no upAxis",
                "location": "[stage.usda]",
                "suggested_fix": None,
                "next_steps": [],
            }
        )
    assert issue.location == layer_location("stage.usda")
    assert issue.strict_promoted is False


# ── result ─────────────────────────────────────────────────────────────────


def _issues(*specs):
    return [
        ValidationIssue(code=code, severity=severity, message=code, location=prim_location(path))
        for code, severity, path in specs
    ]


def test_summary_counts_every_severity_and_always_has_all_keys():
    summary = summarize_issues(
        _issues(
            ("UNRESOLVED_REFERENCE", "error", "/A"),
            ("MISSING_UP_AXIS", "warning", "/B"),
            ("UNBOUND_MATERIAL", "warning", "/C"),
        )
    )
    assert summary == {"error": 1, "warning": 2, "info": 0, "total": 3}
    # An empty stage still yields every key, so callers need no .get() guard.
    assert summarize_issues([]) == {"error": 0, "warning": 0, "info": 0, "total": 0}


def test_success_is_false_only_when_an_error_exists():
    """Warnings never invalidate a stage on their own."""
    warnings_only = ValidationResult.from_issues("shot.usda", _issues(("MISSING_UP_AXIS", "warning", "/B")))
    assert warnings_only.success is True
    assert warnings_only.summary["error"] == 0

    with_error = ValidationResult.from_issues("shot.usda", _issues(("UNRESOLVED_REFERENCE", "error", "/A")))
    assert with_error.success is False


def test_message_summarizes_the_non_zero_severities():
    assert format_summary_message({"error": 1, "warning": 2, "info": 0, "total": 3}) == "3 issues (1 error, 2 warnings)"
    assert format_summary_message({"error": 1, "warning": 0, "info": 0, "total": 1}) == "1 issue (1 error)"
    assert format_summary_message({"error": 0, "warning": 0, "info": 0, "total": 0}) == "No validation issues"


def test_result_aggregates_next_steps_without_duplicates():
    """Two issues of one rule with identical arguments are a single action."""
    steps = [{"action": "manual_fix", "detail": "Set upAxis"}]
    result = ValidationResult.from_issues(
        "shot.usda",
        [
            ValidationIssue(
                code="MISSING_UP_AXIS",
                severity="warning",
                message="first",
                location=layer_location("a.usda"),
                next_steps=steps,
            ),
            ValidationIssue(
                code="MISSING_UP_AXIS",
                severity="warning",
                message="second",
                location=layer_location("b.usda"),
                next_steps=steps,
            ),
            ValidationIssue(
                code="UNBOUND_MATERIAL",
                severity="warning",
                message="third",
                location=prim_location("/Looks/M"),
                next_steps=[{"action": "manual_fix", "detail": "Bind the material"}],
            ),
        ],
    )

    assert result.next_steps == [
        {"action": "manual_fix", "detail": "Set upAxis"},
        {"action": "manual_fix", "detail": "Bind the material"},
    ]
    # Aggregation drops duplicates, never distinct actions.
    assert aggregate_next_steps(result.issues) == result.next_steps


def test_result_payload_carries_the_schema_and_extra_metadata():
    result = ValidationResult.from_issues(
        "shot.usda",
        _issues(("UNRESOLVED_REFERENCE", "error", "/A")),
        extra={"runtime": "pxr", "rules": ["UNRESOLVED_REFERENCE"]},
    )
    payload = result.to_dict()

    assert payload["success"] is False
    assert payload["message"] == "1 issue (1 error)"
    assert payload["stage_file"] == "shot.usda"
    assert payload["summary"] == {"error": 1, "warning": 0, "info": 0, "total": 1}
    assert payload["next_steps"] == []
    # Adapter metadata rides along without being able to shadow a schema key.
    assert payload["runtime"] == "pxr"
    assert payload["rules"] == ["UNRESOLVED_REFERENCE"]

    restored = ValidationResult.from_value(payload)
    assert restored.to_dict() == payload
    assert restored.extra["runtime"] == "pxr"


def test_extra_never_shadows_a_schema_key():
    result = ValidationResult.from_issues("shot.usda", [], extra={"success": True, "message": "overridden"})
    payload = result.to_dict()
    assert payload["message"] == "No validation issues"


def test_empty_result_is_a_success():
    payload = ValidationResult.from_issues("shot.usda", []).to_dict()
    assert payload["success"] is True
    assert payload["issues"] == []
    assert payload["summary"]["total"] == 0


def test_result_is_json_serializable():
    """The payload crosses the MCP boundary as JSON with no custom encoder."""
    payload = validate_stage(str(BROKEN_REFERENCE))
    assert json.loads(json.dumps(payload)) == payload


# ── core ToolResultEnvelope mapping ────────────────────────────────────────


def _envelope_for(sample: Path, strict: bool = False):
    return to_tool_result_envelope(ValidationResult.from_value(validate_stage(str(sample), strict=strict)))


def test_envelope_maps_a_failing_stage():
    envelope = _envelope_for(BROKEN_REFERENCE)
    payload = envelope.to_dict()

    assert payload["success"] is False
    assert payload["error"] == VALIDATION_FAILED
    assert payload["message"] == envelope.context["message"]
    # Structured diagnostics live in context, not in _meta.
    assert payload["context"]["summary"]["error"] >= 1
    assert "_meta" not in payload
    # validate_stage is a read: it must never claim a postcondition.
    assert "postcondition" not in payload


def test_envelope_maps_a_clean_stage():
    envelope = to_tool_result_envelope(ValidationResult.from_issues("shot.usda", []))

    assert envelope.success is True
    assert envelope.error is None
    assert envelope.message == "No validation issues"
    assert envelope.to_dict(prune_empty=False)["error"] is None


def test_envelope_error_is_always_a_string_or_none():
    """The core envelope invariant: ``error`` is a string when present."""
    for sample in (BROKEN_REFERENCE, UNBOUND_MATERIAL, UNIT_MISMATCH):
        for strict in (False, True):
            error = _envelope_for(sample, strict=strict).error
            assert error is None or isinstance(error, str), sample.name
    assert to_tool_result_envelope(ValidationResult.from_issues("s.usda", [])).error is None


def test_envelope_keeps_adapter_metadata_in_context():
    """``runtime`` and ``rules`` survive the mapping into ``context``."""
    payload = _envelope_for(UNBOUND_MATERIAL).to_dict()
    assert payload["context"]["runtime"] in {"pxr", "text-fallback"}
    assert payload["context"]["rules"] == sorted(VALIDATION_RULES)
    # The deprecated aliases stay reachable through the mapping.
    assert payload["context"]["valid"] == payload["success"]
    assert payload["context"]["issue_count"] == payload["context"]["summary"]["total"]


def test_envelope_round_trips_through_the_core_validator():
    """The produced dict is accepted by core's own strict envelope parser."""
    from dcc_mcp_core.result_envelope import ToolResultEnvelope

    payload = _envelope_for(BROKEN_REFERENCE).to_dict(prune_empty=False)
    restored = ToolResultEnvelope.from_dict(payload, strict=True)
    assert restored.success is False
    assert restored.error == VALIDATION_FAILED
    assert restored.context["issues"] == payload["context"]["issues"]


# ── validate_stage, end to end ─────────────────────────────────────────────


def test_validate_stage_returns_the_validation_result_schema():
    payload = validate_stage(str(BROKEN_REFERENCE))
    result = ValidationResult.from_value(payload)

    assert payload["success"] is False
    assert payload["message"] == result.message
    assert payload["stage_file"] == str(BROKEN_REFERENCE)
    assert payload["summary"]["total"] == len(payload["issues"])
    for issue in payload["issues"]:
        # Every emitted issue passes the schema class unchanged.
        assert ValidationIssue.from_value(issue).to_dict() == issue


def test_validate_stage_keeps_the_deprecated_aliases():
    payload = validate_stage(str(UNBOUND_MATERIAL))
    assert payload["valid"] == payload["success"]
    assert payload["issue_count"] == payload["summary"]["total"]
    assert payload["runtime"] in {"pxr", "text-fallback"}
    assert payload["rules"] == sorted(VALIDATION_RULES)


def _load_script(relative_path: str):
    """Load a skill tool script the way the runtime does."""
    import importlib.util

    path = Path(__file__).parents[1] / "src" / "dcc_mcp_openusd" / "skills" / relative_path
    spec = importlib.util.spec_from_file_location("openusd_validation_tool", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the shipped tool surface ───────────────────────────────────────────────


def test_validate_stage_tool_maps_the_result_onto_the_envelope():
    """The skill script is what an agent receives; assert on its envelope."""
    tool = _load_script("openusd-validate/scripts/validate_stage.py")

    result = tool.main(stage_file=str(BROKEN_REFERENCE))

    assert result["success"] is False
    assert result["error"] == VALIDATION_FAILED
    assert result["context"]["summary"]["error"] >= 1
    assert result["context"]["issues"][0]["location"]["kind"] == "prim"
    # An agent can act on the aggregate without walking ``issues``.
    assert result["context"]["next_steps"][0]["action"]
    assert "_meta" not in result
    assert "postcondition" not in result, "validation is a read, not a mutation"


def test_validate_stage_tool_succeeds_on_a_clean_stage(tmp_path):
    """A stage with no error-severity issue is a success with ``error=None``."""
    from dcc_mcp_openusd.runtime import create_stage

    tool = _load_script("openusd-validate/scripts/validate_stage.py")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="valid")

    result = tool.main(stage_file=str(stage_file))

    assert result["success"] is True
    assert result["error"] is None
    assert result["context"]["issues"] == []
    assert result["context"]["summary"]["error"] == 0


@pytest.fixture
def metadata_less_stage(tmp_path):
    """A stage with no root-layer metadata, so both strict rules fire."""
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text('#usda 1.0\n(\n)\n\ndef Xform "World"\n{\n}\n', encoding="utf-8")
    return stage_file


def test_strict_promotes_severity_and_flags_the_issue(metadata_less_stage):
    relaxed = ValidationResult.from_value(validate_stage(str(metadata_less_stage)))
    strict = ValidationResult.from_value(validate_stage(str(metadata_less_stage), strict=True))

    def issue_in(result, code):
        return next(issue for issue in result.issues if issue.code == code)

    assert issue_in(relaxed, "MISSING_UP_AXIS").severity == "warning"
    assert issue_in(relaxed, "MISSING_UP_AXIS").strict_promoted is False

    assert issue_in(strict, "MISSING_UP_AXIS").severity == "error"
    assert issue_in(strict, "MISSING_UP_AXIS").strict_promoted is True
    assert issue_in(strict, "MISSING_METERS_PER_UNIT").strict_promoted is True
    # A rule that is an error on its own is never reported as promoted.
    assert issue_in(strict, "MISSING_DEFAULT_PRIM").strict_promoted is False
    assert relaxed.success is False and strict.success is False
