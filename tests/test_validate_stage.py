"""validate_stage rule coverage.

The rule set must be identical whether or not pxr is installed, so every
behavioural test runs against both runtimes by monkeypatching the cached
``RuntimeInfo``. No test is skipped: when pxr is genuinely absent both
parametrisations exercise the text-fallback collector, which is exactly what a
minimal environment supports.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from dcc_mcp_openusd.runtime import (
    VALIDATION_RULES,
    RuntimeInfo,
    _detect_reference_cycle,
    create_stage,
    detect_runtime,
    validate_stage,
)

#: Captured before any fixture mutates the cached runtime info.
REAL_HAS_PXR = detect_runtime().has_pxr

DATA_DIR = Path(__file__).parent / "data" / "usd"

BROKEN_REFERENCE = DATA_DIR / "broken_reference.usda"
UNIT_MISMATCH = DATA_DIR / "unit_mismatch.usda"
UNBOUND_MATERIAL = DATA_DIR / "unbound_material.usda"


@pytest.fixture(params=["pxr", "text-fallback"])
def runtime_mode(request, monkeypatch):
    """Run the test once per runtime by forcing the detected runtime."""
    monkeypatch.setattr(
        "dcc_mcp_openusd.runtime._RUNTIME_INFO",
        RuntimeInfo(has_pxr=request.param == "pxr"),
    )
    return request.param


def codes(result) -> set:
    return {issue["code"] for issue in result["issues"]}


def issue_for(result, code: str):
    matches = [issue for issue in result["issues"] if issue["code"] == code]
    assert matches, f"expected {code} in {[i['code'] for i in result['issues']]}"
    return matches[0]


# ── rule registry and issue shape ──────────────────────────────────────────


def test_rule_registry_is_exposed():
    """validate_stage must advertise the rule codes it can emit."""
    assert len(VALIDATION_RULES) >= 5, "MVP requires at least five validators"
    result = validate_stage(str(BROKEN_REFERENCE))
    assert result["rules"] == sorted(VALIDATION_RULES)


def test_issue_objects_keep_severity_and_message_and_add_code_and_location(runtime_mode, tmp_path):
    """Issues stay backwards compatible and gain code + location."""
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text('#usda 1.0\n(\n)\n\ndef Xform "World"\n{\n}\n', encoding="utf-8")

    result = validate_stage(str(stage_file))
    assert result["issues"], "expected at least one issue for a metadata-less stage"

    for issue in result["issues"]:
        assert set(issue) == {"code", "severity", "message", "location"}
        assert issue["code"] in VALIDATION_RULES
        assert issue["severity"] in {"error", "warning"}
        assert issue["message"]
        assert issue["location"]


def test_pxr_and_fallback_report_the_same_codes_on_every_fixture():
    """Both runtimes must run the same rules over the same sample stages."""
    for sample in (BROKEN_REFERENCE, UNIT_MISMATCH, UNBOUND_MATERIAL):
        pxr_result = _validate_with(sample, has_pxr=True)
        fallback_result = _validate_with(sample, has_pxr=False)
        assert codes(pxr_result) == codes(fallback_result), sample.name
        assert [i["severity"] for i in pxr_result["issues"]] == [i["severity"] for i in fallback_result["issues"]], (
            sample.name
        )


def _validate_with(sample: Path, has_pxr: bool, strict: bool = False):
    import dcc_mcp_openusd.runtime as runtime_module

    original = runtime_module._RUNTIME_INFO
    runtime_module._RUNTIME_INFO = RuntimeInfo(has_pxr=has_pxr)
    try:
        return validate_stage(str(sample), strict=strict)
    finally:
        runtime_module._RUNTIME_INFO = original


# ── clean stage baseline ───────────────────────────────────────────────────


def test_authored_stage_is_valid_in_strict_mode(runtime_mode, tmp_path):
    """A stage produced by create_stage raises no error, even under strict."""
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="valid")

    result = validate_stage(str(stage_file), strict=True)
    assert result["valid"] is True
    assert [i for i in result["issues"] if i["severity"] == "error"] == []


def test_runtime_label_matches_the_forced_runtime(runtime_mode, tmp_path):
    """The reported runtime reflects the collector that actually ran."""
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="runtime-label")
    result = validate_stage(str(stage_file))
    expected = "pxr" if (runtime_mode == "pxr" and REAL_HAS_PXR) else "text-fallback"
    assert result["runtime"] == expected


# ── high-frequency error 1: broken references ───────────────────────────────


def test_broken_reference_is_reported(runtime_mode):
    """A reference that cannot be resolved on disk is an error."""
    result = validate_stage(str(BROKEN_REFERENCE))

    assert result["valid"] is False
    issue = issue_for(result, "UNRESOLVED_REFERENCE")
    assert issue["severity"] == "error"
    assert issue["location"] == "/World/SetDressing/MissingSetPiece"
    assert "missing_set_piece.usda" in issue["message"]


def test_resolvable_reference_is_not_reported(runtime_mode, tmp_path):
    """The same stage with the asset present validates clean."""
    stage_file = tmp_path / "scene.usda"
    (tmp_path / "assets").mkdir()
    shutil.copyfile(BROKEN_REFERENCE, stage_file)
    shutil.copyfile(UNIT_MISMATCH, tmp_path / "assets" / "missing_set_piece.usda")

    result = validate_stage(str(stage_file))
    assert "UNRESOLVED_REFERENCE" not in codes(result)


def test_reference_cycle_is_reported(runtime_mode, tmp_path):
    """A stage that references itself is a composition cycle."""
    stage_file = tmp_path / "cycle.usda"
    stage_file.write_text(
        "#usda 1.0\n"
        "(\n"
        '    defaultPrim = "World"\n'
        "    metersPerUnit = 1\n"
        '    upAxis = "Y"\n'
        ")\n\n"
        'def Xform "World"\n'
        "{\n"
        '    def Xform "Loop" (\n'
        "        prepend references = @./cycle.usda@\n"
        "    )\n"
        "    {\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = validate_stage(str(stage_file))
    assert "REFERENCE_CYCLE" in codes(result)
    assert issue_for(result, "REFERENCE_CYCLE")["location"] == "[cycle.usda]"


def test_detect_reference_cycle_returns_none_for_acyclic_stage(tmp_path):
    """The cycle walker stays quiet on a healthy reference graph."""
    assert _detect_reference_cycle(BROKEN_REFERENCE) is None
    assert _detect_reference_cycle(tmp_path / "does_not_exist.usda") is None


# ── high-frequency error 2: unit / up-axis inconsistency ───────────────────


def test_up_axis_mismatch_is_reported(runtime_mode):
    """A sublayer declaring a different upAxis is an error."""
    result = validate_stage(str(UNIT_MISMATCH))

    issue = issue_for(result, "UP_AXIS_MISMATCH")
    assert issue["severity"] == "error"
    assert issue["location"] == "[unit_mismatch_sublayer.usda]"
    assert "Z" in issue["message"] and "Y" in issue["message"]


def test_meters_per_unit_mismatch_is_reported(runtime_mode):
    """A sublayer declaring a different metersPerUnit is an error."""
    result = validate_stage(str(UNIT_MISMATCH))

    issue = issue_for(result, "METERS_PER_UNIT_MISMATCH")
    assert issue["severity"] == "error"
    assert issue["location"] == "[unit_mismatch_sublayer.usda]"
    assert "0.01" in issue["message"]


def test_matching_sublayer_metadata_is_not_reported(runtime_mode, tmp_path):
    """A sublayer that agrees with the root layer raises no mismatch."""
    stage_file = tmp_path / "scene.usda"
    sublayer = tmp_path / "sub.usda"
    sublayer.write_text(
        '#usda 1.0\n(\n    metersPerUnit = 0.01\n    upAxis = "Z"\n)\n\ndef Xform "Props"\n{\n}\n',
        encoding="utf-8",
    )
    stage_file.write_text(
        "#usda 1.0\n(\n"
        '    defaultPrim = "World"\n'
        "    metersPerUnit = 0.01\n"
        "    subLayers = [@./sub.usda@]\n"
        '    upAxis = "Z"\n)\n\n'
        'def Xform "World"\n{\n}\n',
        encoding="utf-8",
    )

    result = validate_stage(str(stage_file))
    assert "UP_AXIS_MISMATCH" not in codes(result)
    assert "METERS_PER_UNIT_MISMATCH" not in codes(result)


def test_invalid_up_axis_is_reported(runtime_mode, tmp_path):
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        "#usda 1.0\n(\n"
        '    defaultPrim = "World"\n'
        "    metersPerUnit = 1\n"
        '    upAxis = "W"\n)\n\n'
        'def Xform "World"\n{\n}\n',
        encoding="utf-8",
    )

    issue = issue_for(validate_stage(str(stage_file)), "INVALID_UP_AXIS")
    assert issue["severity"] == "error"


def test_invalid_meters_per_unit_is_reported(runtime_mode, tmp_path):
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        "#usda 1.0\n(\n"
        '    defaultPrim = "World"\n'
        "    metersPerUnit = 0\n"
        '    upAxis = "Y"\n)\n\n'
        'def Xform "World"\n{\n}\n',
        encoding="utf-8",
    )

    issue = issue_for(validate_stage(str(stage_file)), "INVALID_METERS_PER_UNIT")
    assert issue["severity"] == "error"


def test_strict_promotes_missing_production_metadata(runtime_mode, tmp_path):
    """strict=True treats missing upAxis / metersPerUnit as errors."""
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text('#usda 1.0\n(\n)\n\ndef Xform "World"\n{\n}\n', encoding="utf-8")

    relaxed = validate_stage(str(stage_file))
    assert issue_for(relaxed, "MISSING_UP_AXIS")["severity"] == "warning"
    assert issue_for(relaxed, "MISSING_METERS_PER_UNIT")["severity"] == "warning"

    strict = validate_stage(str(stage_file), strict=True)
    assert issue_for(strict, "MISSING_UP_AXIS")["severity"] == "error"
    assert issue_for(strict, "MISSING_METERS_PER_UNIT")["severity"] == "error"
    assert strict["valid"] is False


# ── high-frequency error 3: material binding ───────────────────────────────


def test_dangling_material_binding_is_reported(runtime_mode):
    """A binding targeting a missing Material is an error."""
    result = validate_stage(str(UNBOUND_MATERIAL))

    issue = issue_for(result, "DANGLING_MATERIAL_BINDING")
    assert issue["severity"] == "error"
    assert issue["location"] == "/World/Prop"
    assert "MissingPropPaint" in issue["message"]


def test_material_without_shader_is_reported(runtime_mode):
    """A Material with no surface output is incomplete."""
    result = validate_stage(str(UNBOUND_MATERIAL))

    issue = issue_for(result, "INCOMPLETE_MATERIAL")
    assert issue["severity"] == "warning"
    assert issue["location"] == "/World/Materials/PropPaint"


def test_unbound_material_is_reported(runtime_mode):
    """A Material that nothing binds is reported."""
    result = validate_stage(str(UNBOUND_MATERIAL))

    issue = issue_for(result, "UNBOUND_MATERIAL")
    assert issue["severity"] == "warning"
    assert issue["location"] == "/World/Materials/PropPaint"


def test_bound_and_shaded_material_is_clean(runtime_mode, tmp_path):
    """A bound Material with a connected shader raises no material issue."""
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        "#usda 1.0\n(\n"
        '    defaultPrim = "World"\n'
        "    metersPerUnit = 1\n"
        '    upAxis = "Y"\n)\n\n'
        'def Xform "World"\n'
        "{\n"
        '    def Scope "Materials"\n'
        "    {\n"
        '        def Material "Red"\n'
        "        {\n"
        "            token outputs:surface.connect = </World/Materials/Red/Shader.outputs:surface>\n\n"
        '            def Shader "Shader"\n'
        "            {\n"
        '                uniform token info:id = "UsdPreviewSurface"\n'
        "                token outputs:surface\n"
        "            }\n"
        "        }\n"
        "    }\n\n"
        '    def Mesh "Cube"\n'
        "    {\n"
        "        rel material:binding = </World/Materials/Red>\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = validate_stage(str(stage_file))
    assert result["valid"] is True
    assert {
        "INCOMPLETE_MATERIAL",
        "UNBOUND_MATERIAL",
        "DANGLING_MATERIAL_BINDING",
    }.isdisjoint(codes(result))


def test_binding_to_a_non_material_prim_is_reported(runtime_mode, tmp_path):
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        "#usda 1.0\n(\n"
        '    defaultPrim = "World"\n'
        "    metersPerUnit = 1\n"
        '    upAxis = "Y"\n)\n\n'
        'def Xform "World"\n'
        "{\n"
        '    def Xform "NotAMaterial"\n'
        "    {\n"
        "    }\n\n"
        '    def Mesh "Cube"\n'
        "    {\n"
        "        rel material:binding = </World/NotAMaterial>\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    issue = issue_for(validate_stage(str(stage_file)), "DANGLING_MATERIAL_BINDING")
    assert "not a Material" in issue["message"]


# ── defaultPrim and hierarchy ──────────────────────────────────────────────


def test_missing_default_prim_is_an_error(runtime_mode, tmp_path):
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        '#usda 1.0\n(\n    metersPerUnit = 1\n    upAxis = "Y"\n)\n\ndef Xform "World"\n{\n}\n',
        encoding="utf-8",
    )

    issue = issue_for(validate_stage(str(stage_file)), "MISSING_DEFAULT_PRIM")
    assert issue["severity"] == "error"


def test_default_prim_pointing_at_a_missing_prim_is_reported(runtime_mode, tmp_path):
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        "#usda 1.0\n(\n"
        '    defaultPrim = "Nope"\n'
        "    metersPerUnit = 1\n"
        '    upAxis = "Y"\n)\n\n'
        'def Xform "World"\n{\n}\n',
        encoding="utf-8",
    )

    issue = issue_for(validate_stage(str(stage_file)), "INVALID_DEFAULT_PRIM")
    assert issue["severity"] == "error"
    assert issue["location"] == "/Nope"


def test_untyped_nested_prim_is_reported(runtime_mode, tmp_path):
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        "#usda 1.0\n(\n"
        '    defaultPrim = "World"\n'
        "    metersPerUnit = 1\n"
        '    upAxis = "Y"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def "Holder"\n    {\n    }\n'
        "}\n",
        encoding="utf-8",
    )

    issue = issue_for(validate_stage(str(stage_file)), "UNDEFINED_PRIM_TYPE")
    assert issue["severity"] == "warning"
    assert issue["location"] == "/World/Holder"


def test_empty_stage_reports_no_traversable_prims(runtime_mode, tmp_path):
    stage_file = tmp_path / "empty.usda"
    stage_file.write_text("#usda 1.0\n(\n)\n", encoding="utf-8")

    issue = issue_for(validate_stage(str(stage_file)), "NO_TRAVERSABLE_PRIMS")
    assert issue["severity"] == "warning"
    assert issue["location"] == "/"


def test_non_usda_text_reports_invalid_header(runtime_mode, tmp_path):
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text("not a usd file at all\n", encoding="utf-8")

    issue = issue_for(validate_stage(str(stage_file)), "INVALID_STAGE_HEADER")
    assert issue["severity"] == "error"
    assert issue["location"] == "[line 1]"


def test_comments_are_ignored_when_parsing_metadata(runtime_mode, tmp_path):
    """A '#'-comment before the metadata block must not confuse the parser."""
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        "#usda 1.0\n"
        "# authored by the openusd adapter\n"
        "(\n"
        '    defaultPrim = "World"  # the root\n'
        "    metersPerUnit = 1\n"
        '    upAxis = "Y"\n'
        ")\n\n"
        'def Xform "World"\n{\n}\n',
        encoding="utf-8",
    )

    result = validate_stage(str(stage_file))
    assert result["valid"] is True
    assert "MISSING_DEFAULT_PRIM" not in codes(result)


# ── tool contract guard ────────────────────────────────────────────────────


def test_validate_stage_tool_contract_is_unchanged():
    """tools.yaml must keep the stage_file / strict signature."""
    tools_path = Path(__file__).parents[1] / "src" / "dcc_mcp_openusd" / "skills" / "openusd-validate" / "tools.yaml"
    tools = yaml.safe_load(tools_path.read_text(encoding="utf-8"))["tools"]
    tool = next(item for item in tools if item["name"] == "validate_stage")

    assert tool["input_schema"]["required"] == ["stage_file"]
    assert set(tool["input_schema"]["properties"]) == {"stage_file", "strict"}
    assert tool["input_schema"]["properties"]["strict"]["default"] is False
    assert tool["source_file"] == "scripts/validate_stage.py"
