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
CUSTOM_DATA_PRIM = DATA_DIR / "custom_data_prim.usda"
DEEP_SHADER = DATA_DIR / "deep_shader.usda"
MULTILINE_SUBLAYERS = DATA_DIR / "multiline_sublayers.usda"
NESTED_REFERENCE = DATA_DIR / "nested_reference.usda"
PURPOSE_BINDING = DATA_DIR / "purpose_binding.usda"
SUBLAYER_OFFSET = DATA_DIR / "sublayer_offset.usda"
UNIT_MISMATCH = DATA_DIR / "unit_mismatch.usda"
UNBOUND_MATERIAL = DATA_DIR / "unbound_material.usda"
VARIANT_MATERIAL = DATA_DIR / "variant_material.usda"
VARIANT_NESTED = DATA_DIR / "variant_nested.usda"
VARIANT_MULTI = DATA_DIR / "variant_multi.usda"
VARIANT_SHARED_NAME = DATA_DIR / "variant_shared_name.usda"

#: Every sample stage the parity test compares across runtimes.
SAMPLES = (
    BROKEN_REFERENCE,
    CUSTOM_DATA_PRIM,
    DEEP_SHADER,
    MULTILINE_SUBLAYERS,
    NESTED_REFERENCE,
    PURPOSE_BINDING,
    SUBLAYER_OFFSET,
    UNIT_MISMATCH,
    UNBOUND_MATERIAL,
    VARIANT_MATERIAL,
    VARIANT_NESTED,
    VARIANT_MULTI,
    VARIANT_SHARED_NAME,
)


@pytest.fixture(params=["pxr", "text-fallback"])
def runtime_mode(request, monkeypatch):
    """Run the test once per runtime by forcing the detected runtime.

    The "pxr" parametrisation skips loudly when ``usd-core`` is absent: without
    it validate_stage degrades to the text collector, and the two
    parametrisations would silently compare text against text. CI runs this
    module in the ``test-openusd`` job, where pxr is installed.
    """
    mode = request.param
    if mode == "pxr" and not REAL_HAS_PXR:
        pytest.skip("pxr runtime requested but usd-core is not installed")  # noqa: B028
    monkeypatch.setattr(
        "dcc_mcp_openusd.runtime._RUNTIME_INFO",
        RuntimeInfo(has_pxr=mode == "pxr"),
    )
    return mode


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
        assert set(issue) == {"code", "severity", "message", "location", "suggested_fix", "next_steps"}
        assert issue["code"] in VALIDATION_RULES
        assert issue["severity"] in {"error", "warning"}
        assert issue["message"]
        assert issue["location"]


def test_pxr_and_fallback_report_the_same_codes_on_every_fixture():
    """Both runtimes must run the same rules over the same sample stages.

    This is the only test that can prove the shared-rule-set claim, so it skips
    loudly instead of passing vacuously when ``usd-core`` is unavailable.
    """
    if not REAL_HAS_PXR:
        pytest.skip("runtime parity requires usd-core; the test-openusd CI job provides it")  # noqa: B028

    for sample in SAMPLES:
        pxr_result = _validate_with(sample, has_pxr=True)
        fallback_result = _validate_with(sample, has_pxr=False)
        assert pxr_result["runtime"] == "pxr", sample.name
        assert fallback_result["runtime"] == "text-fallback", sample.name
        assert codes(pxr_result) == codes(fallback_result), sample.name
        assert [i["severity"] for i in pxr_result["issues"]] == [i["severity"] for i in fallback_result["issues"]], (
            sample.name
        )
        assert [i["location"] for i in pxr_result["issues"]] == [i["location"] for i in fallback_result["issues"]], (
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
    assert result["runtime"] == runtime_mode


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


# ── collector equivalence regressions ──────────────────────────────────────
#
# Each test below pins one defect that made the pxr and text collectors disagree
# while the parity test was passing vacuously. They are grouped by the review
# finding they close.


def test_prim_header_dictionary_does_not_swallow_the_body(runtime_mode):
    """A ``customData = { ... }`` header must not shift the prim body.

    The body brace used to be located with the first ``{``, which landed inside
    the header dictionary; the real body then leaked into the parent prim and
    the broken reference was reported against /World instead of /World/Body.
    """
    result = validate_stage(str(CUSTOM_DATA_PRIM))

    issue = issue_for(result, "UNRESOLVED_REFERENCE")
    assert issue["location"] == "/World/Body"
    # The prim header dictionary also carries the binding, which must be seen.
    assert "DANGLING_MATERIAL_BINDING" not in codes(result)


def test_sublayer_offset_does_not_truncate_layer_metadata(runtime_mode):
    """``subLayers = [@x@ (offset = N)]`` must not cut the metadata block.

    Stopping at the first ``)`` dropped ``upAxis``, which produced a false
    MISSING_UP_AXIS and hid the real UP_AXIS_MISMATCH.
    """
    result = validate_stage(str(SUBLAYER_OFFSET), strict=True)

    assert "MISSING_UP_AXIS" not in codes(result)
    assert "MISSING_METERS_PER_UNIT" not in codes(result)
    assert issue_for(result, "UP_AXIS_MISMATCH")["location"] == "[sublayer_offset_sub.usda]"
    assert issue_for(result, "METERS_PER_UNIT_MISMATCH")["severity"] == "error"


def test_resolvable_nested_reference_is_not_reported(runtime_mode):
    """A reference authored in a nested layer resolves against its own layer.

    Every asset path is authored in the root layer and therefore resolved
    against the root layer directory; resolving a nested layer's relative path
    against the root directory produced a false UNRESOLVED_REFERENCE.
    """
    result = validate_stage(str(NESTED_REFERENCE))

    assert "UNRESOLVED_REFERENCE" not in codes(result)
    assert "REFERENCE_CYCLE" not in codes(result)


def test_purpose_specific_binding_counts_as_bound(runtime_mode):
    """``material:binding:preview`` binds the material in both runtimes.

    pxr used to accept only the exact ``material:binding`` name, so a stage
    bound by purpose alone got a spurious UNBOUND_MATERIAL warning.
    """
    result = validate_stage(str(PURPOSE_BINDING))

    assert "UNBOUND_MATERIAL" not in codes(result)
    assert "INCOMPLETE_MATERIAL" not in codes(result)


def test_collection_binding_is_not_treated_as_a_material_binding(runtime_mode):
    """``material:binding:collection:*`` targets a collection, not a material.

    Both runtimes must ignore it — otherwise the dangling collection target in
    the sample stage would be reported as DANGLING_MATERIAL_BINDING.
    """
    result = validate_stage(str(PURPOSE_BINDING))

    assert "DANGLING_MATERIAL_BINDING" not in codes(result)


def test_binding_name_filter_is_shared_by_both_collectors():
    """The pxr and text collectors must accept the same relationship names."""
    from dcc_mcp_openusd.runtime import _is_material_binding_name

    assert _is_material_binding_name("material:binding")
    assert _is_material_binding_name("material:binding:preview")
    assert _is_material_binding_name("material:binding:full")
    assert not _is_material_binding_name("material:binding:collection:proxy")
    assert not _is_material_binding_name("material:binding:collection")
    assert not _is_material_binding_name("material:displacement")


def _layer(up_axis: str) -> str:
    """Return a minimal USDA layer declaring only *up_axis*."""
    return f'#usda 1.0\n(\n    upAxis = "{up_axis}"\n)\n\ndef Xform "Props"\n{{\n}}\n'


def test_sublayers_differing_only_by_case_are_both_checked(runtime_mode, tmp_path):
    """Distinct sublayer files that differ only by case must both be checked.

    ``_layer_key`` used to lowercase unconditionally, which collapsed
    ``Set.usda`` and ``set.usda`` into one node in the layer chain and dropped
    one of the two mismatch reports. Both files are really created here and the
    assertion would fail if the keys were merged, so the test can fail.
    """
    import os

    from dcc_mcp_openusd.runtime import _layer_key

    upper = tmp_path / "Set.usda"
    lower = tmp_path / "set.usda"
    if os.path.normcase(upper.name) == os.path.normcase(lower.name):
        pytest.skip("case-insensitive filesystem: the two names are one file")  # noqa: B028

    upper.write_text(_layer("Z"), encoding="utf-8")
    lower.write_text(_layer("X"), encoding="utf-8")
    assert _layer_key(upper) != _layer_key(lower)

    root = tmp_path / "scene.usda"
    root.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n    metersPerUnit = 1\n'
        "    subLayers = [@./Set.usda@, @./set.usda@]\n"
        '    upAxis = "Y"\n)\n\n'
        'def Xform "World"\n{\n}\n',
        encoding="utf-8",
    )

    result = validate_stage(str(root))
    locations = {issue["location"] for issue in result["issues"] if issue["code"] == "UP_AXIS_MISMATCH"}
    assert locations == {"[Set.usda]", "[set.usda]"}


def test_material_defined_in_a_variant_block_is_visible(runtime_mode):
    """A Material authored inside a variantSet must resolve in both runtimes.

    The pxr walk only followed ``nameChildren``, so variant content was
    invisible to it and the binding looked dangling — an error that flipped
    ``valid`` to False. Both collectors now report variant prims at the flat
    path they compose to.
    """
    result = validate_stage(str(VARIANT_MATERIAL))

    assert "DANGLING_MATERIAL_BINDING" not in codes(result)
    assert result["valid"] is True


def test_multiple_variants_flatten_to_the_same_level(runtime_mode):
    """Two variants on one prim must flatten, not nest inside each other.

    The text collector inferred prim nesting from raw brace depth, but
    ``variantSet = {`` and each ``\"name\" {`` add a brace level that is not a
    prim level. The first variant happened to line up; the second was nested
    under it, so a binding to the second variant's material looked dangling —
    an error that flipped ``valid`` to False.
    """
    result = validate_stage(str(VARIANT_MULTI))

    assert "DANGLING_MATERIAL_BINDING" not in codes(result)
    assert result["valid"] is True
    # Both materials are reported at the flat path they compose to.
    unbound = {issue["location"] for issue in result["issues"] if issue["code"] == "UNBOUND_MATERIAL"}
    assert unbound == {"/Root/Looks/RedMat"}


def test_nested_variant_sets_are_counted_once(runtime_mode):
    """A variantSet nested inside another must not be double-counted.

    Scanning a variantSet's whole body also matches the entries of any nested
    set, which then get claimed again when the nested set is visited — so the
    discount over-subtracts and prims land one level too high, making a valid
    binding look dangling (an error that flips ``valid``).
    """
    result = validate_stage(str(VARIANT_NESTED))

    assert "DANGLING_MATERIAL_BINDING" not in codes(result)
    assert result["valid"] is True


def test_variant_spans_are_not_double_counted():
    """Each variantSet and variant block contributes exactly one span."""
    from dcc_mcp_openusd.runtime import _variant_block_spans

    text = VARIANT_NESTED.read_text(encoding="utf-8")
    spans = _variant_block_spans(text)

    assert len(spans) == len(set(spans)), f"duplicate spans: {spans}"
    # One span each for the two variantSet blocks and the two variant entries.
    assert len(spans) == 4
    assert sum(1 for start, _ in spans if text.startswith("variantSet", start)) == 2


def test_braces_inside_strings_do_not_shift_prim_nesting():
    """A brace inside a quoted value must not be read as nesting.

    The depth array has to skip quoted strings and @asset@ paths the same way
    _matching_delimiter() does, otherwise a brace in a customData value
    de-balances the nesting level of every prim authored after it.
    """
    from dcc_mcp_openusd.runtime import _parse_usda_blocks

    text = (
        '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Mesh "Body" (\n        customData = { string note = "}" }\n    )\n    {\n    }\n\n'
        '    def Mesh "Other"\n    {\n    }\n'
        "}\n"
    )
    paths = [block["path"] for block in _parse_usda_blocks(text)]
    assert paths == ["/World", "/World/Body", "/World/Other"]


def test_prim_types_are_flat_under_multiple_variants():
    """The text parser must not nest a second variant under the first."""
    from dcc_mcp_openusd.runtime import _parse_usda_blocks

    text = VARIANT_MULTI.read_text(encoding="utf-8")
    paths = [block["path"] for block in _parse_usda_blocks(text)]

    assert "/Root/Looks/RedMat" in paths
    assert "/Root/Looks/BlueMat" in paths
    # Nothing from the blue variant may hang off the red one.
    assert not [path for path in paths if path.startswith("/Root/Looks/RedMat/") and "BlueMat" in path]


def test_same_named_prim_in_two_variants_merges(runtime_mode):
    """A name authored in several variants collapses onto one path.

    The collectors used to overwrite on collision, so an empty second variant
    discarded the complete first one and produced a false
    INCOMPLETE_MATERIAL. Types keep the first non-empty value and material
    completeness is OR-ed, so variant order cannot change the verdict.
    """
    result = validate_stage(str(VARIANT_SHARED_NAME))

    assert "INCOMPLETE_MATERIAL" not in codes(result)
    assert result["valid"] is True


def test_merge_prim_type_keeps_the_first_non_empty_value():
    """The merge helper must not let an empty type overwrite a real one."""
    from dcc_mcp_openusd.runtime import _merge_prim_type

    assert _merge_prim_type(None, "Mesh") == "Mesh"
    assert _merge_prim_type("Mesh", "") == "Mesh"
    assert _merge_prim_type("", "Mesh") == "Mesh"
    assert _merge_prim_type("Xform", "Mesh") == "Xform"
    assert _merge_prim_type("", "") == ""


def test_shader_nested_deeper_than_a_direct_child_counts(runtime_mode):
    """A Shader several levels below its Material counts as its surface.

    The pxr collector only collected direct children while the text collector
    matched on path prefix at any depth, so a Shader inside a NodeGraph was a
    spurious INCOMPLETE_MATERIAL under pxr alone.
    """
    result = validate_stage(str(DEEP_SHADER))

    assert "INCOMPLETE_MATERIAL" not in codes(result)
    assert "UNBOUND_MATERIAL" not in codes(result)
    assert result["valid"] is True


def test_multiline_sublayers_are_all_parsed(runtime_mode):
    """A subLayers list written across several lines must not collapse.

    The regex stopped at the end of the line, so a multi-line list yielded no
    sublayers at all and both unit-consistency checks were silently skipped —
    a false negative against acceptance criterion 3.
    """
    result = validate_stage(str(MULTILINE_SUBLAYERS))

    mismatches = {issue["location"] for issue in result["issues"] if issue["code"] == "UP_AXIS_MISMATCH"}
    assert mismatches == {"[sub_a.usda]", "[sub_b.usda]"}
    units = {issue["location"] for issue in result["issues"] if issue["code"] == "METERS_PER_UNIT_MISMATCH"}
    assert units == {"[sub_a.usda]", "[sub_b.usda]"}
    assert result["valid"] is False


def test_sublayer_assets_parse_across_line_breaks():
    """The subLayers parser handles multi-line, single-line and bare forms."""
    from dcc_mcp_openusd.runtime import _find_sublayer_assets

    assert _find_sublayer_assets("subLayers = [\n    @./a.usda@,\n    @./b.usda@\n]") == [
        "./a.usda",
        "./b.usda",
    ]
    assert _find_sublayer_assets("subLayers = [@./a.usda@, @./b.usda@]") == ["./a.usda", "./b.usda"]
    assert _find_sublayer_assets("subLayers = [@./a.usda@ (offset = 10; scale = 1)]") == ["./a.usda"]
    assert _find_sublayer_assets("subLayers = @./a.usda@") == ["./a.usda"]
    assert _find_sublayer_assets("metersPerUnit = 1") == []


def test_referenced_prims_are_out_of_scope_for_both_collectors(runtime_mode, tmp_path):
    """Prims composed in from a reference are not reported by either runtime.

    pxr used to traverse the composed stage while the text collector only saw
    the root layer, so material and defaultPrim facts diverged.
    """
    asset = tmp_path / "asset.usda"
    asset.write_text(
        '#usda 1.0\n(\n    defaultPrim = "Asset"\n)\n\n'
        'def Xform "Asset"\n{\n    def Material "AssetMat"\n    {\n    }\n}\n',
        encoding="utf-8",
    )
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text(
        '#usda 1.0\n(\n    defaultPrim = "World"\n    metersPerUnit = 1\n    upAxis = "Y"\n)\n\n'
        'def Xform "World"\n{\n'
        '    def Xform "Placed" (\n        prepend references = @./asset.usda@\n    )\n    {\n    }\n'
        "}\n",
        encoding="utf-8",
    )

    result = validate_stage(str(stage_file))
    # /World/Placed/AssetMat lives in the referenced layer, not the root layer.
    assert "UNBOUND_MATERIAL" not in codes(result)
    assert "INCOMPLETE_MATERIAL" not in codes(result)
    assert result["valid"] is True


# ── suggested_fix / next_steps wiring ──────────────────────────────────────


def test_unresolved_reference_points_at_the_reference_fix_skill(runtime_mode):
    """A broken reference suggests fix_reference_path with the prim that owns it."""
    result = validate_stage(str(BROKEN_REFERENCE))

    issue = issue_for(result, "UNRESOLVED_REFERENCE")
    assert issue["suggested_fix"] == {
        "skill": "openusd_stage__fix_reference_path",
        "args": {
            "stage_file": str(BROKEN_REFERENCE),
            "prim_path": "/World/SetDressing/MissingSetPiece",
        },
    }
    assert issue["next_steps"][0]["action"] == "openusd_stage__fix_reference_path"
    assert issue["next_steps"][0]["args"]["prim_path"] == "/World/SetDressing/MissingSetPiece"


def test_material_issues_point_at_the_material_fix_skill(runtime_mode):
    """Both material rules suggest suggest_material_bind with the prim involved."""
    result = validate_stage(str(UNBOUND_MATERIAL))

    dangling = issue_for(result, "DANGLING_MATERIAL_BINDING")
    assert dangling["suggested_fix"]["skill"] == "openusd_material__suggest_material_bind"
    assert dangling["suggested_fix"]["args"] == {
        "stage_file": str(UNBOUND_MATERIAL),
        "prim_path": "/World/Prop",
    }

    unbound = issue_for(result, "UNBOUND_MATERIAL")
    assert unbound["suggested_fix"]["skill"] == "openusd_material__suggest_material_bind"
    assert unbound["suggested_fix"]["args"] == {
        "stage_file": str(UNBOUND_MATERIAL),
        "material_path": "/World/Materials/PropPaint",
    }


def test_rules_without_a_fix_skill_still_carry_guidance(runtime_mode, tmp_path):
    """Every rule yields next_steps, so an agent is never left without a next move."""
    stage_file = tmp_path / "scene.usda"
    stage_file.write_text('#usda 1.0\n(\n    defaultPrim = "World"\n)\n\ndef Xform "World"\n{\n}\n', encoding="utf-8")

    result = validate_stage(str(stage_file))
    assert result["issues"]
    for issue in result["issues"]:
        assert issue["next_steps"], issue["code"]
        assert issue["next_steps"][0]["action"]

    missing_axis = issue_for(result, "MISSING_UP_AXIS")
    assert missing_axis["suggested_fix"] is None
    assert missing_axis["next_steps"][0]["action"] == "manual_fix"
    assert "upAxis" in missing_axis["next_steps"][0]["detail"]


def test_suggested_fix_matches_across_runtimes():
    """The fix wiring is runtime-independent, like every other issue field."""
    if not REAL_HAS_PXR:
        pytest.skip("runtime parity requires usd-core; the test-openusd CI job provides it")  # noqa: B028

    for sample in (BROKEN_REFERENCE, UNBOUND_MATERIAL):
        pxr_result = _validate_with(sample, has_pxr=True)
        fallback_result = _validate_with(sample, has_pxr=False)
        assert [i["suggested_fix"] for i in pxr_result["issues"]] == [
            i["suggested_fix"] for i in fallback_result["issues"]
        ], sample.name
        assert [i["next_steps"] for i in pxr_result["issues"]] == [
            i["next_steps"] for i in fallback_result["issues"]
        ], sample.name
