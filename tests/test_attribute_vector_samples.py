"""Real pxr regressions for JSON scalar-vector attribute time samples."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("pxr")
from pxr import Gf, Sdf, Usd  # noqa: E402

from dcc_mcp_openusd.runtime import OpenUsdError, author_attribute_samples, create_stage, define_prim  # noqa: E402


@pytest.mark.parametrize(
    "type_name,value",
    [
        ("Float2", [0.25, 0.75]),
        ("Double2", [0, 1]),
        ("Color3f", [0.1, 0.2, 0.3]),
        ("Normal3f", [0, 1, 0]),
        ("TexCoord2h", [0.25, 0.75]),
        ("Float4", [1, 2, 3, 4]),
        ("Int3", [1, 2, 3]),
    ],
)
def test_json_vector_samples_survive_save_reopen(tmp_path, type_name, value):
    path = str(tmp_path / "vector.usda")
    create_stage(path)
    stage = Usd.Stage.Open(path)
    attr = stage.GetPrimAtPath("/World").CreateAttribute("test:value", getattr(Sdf.ValueTypeNames, type_name))
    stage.GetRootLayer().Save()
    del attr, stage
    # JSON transport must not rely on callers constructing Gf values.
    samples = json.loads(json.dumps([{"time": 1, "value": value}, {"time": 2, "value": value}]))
    result = author_attribute_samples(path, "/World", "test:value", samples)
    stage = Usd.Stage.Open(path)
    attr = stage.GetPrimAtPath("/World").GetAttribute("test:value")
    assert result["runtime"] == "pxr"
    assert attr.GetTimeSamples() == [1.0, 2.0]
    assert list(attr.Get(1)) == pytest.approx(value, abs=1e-3)
    assert attr.GetTypeName() == getattr(Sdf.ValueTypeNames, type_name)


def test_schema_vector_sample_nurbs_patch_range(tmp_path):
    path = str(tmp_path / "patch.usda")
    create_stage(path)
    define_prim(path, "/World/Patch", "NurbsPatch")
    author_attribute_samples(path, "/World/Patch", "uRange", [{"time": 1, "value": [0, 1]}])
    stage = Usd.Stage.Open(path)
    assert stage.GetPrimAtPath("/World/Patch").GetAttribute("uRange").Get(1) == Gf.Vec2d(0, 1)


@pytest.mark.parametrize("dimension", [2, 3, 4])
@pytest.mark.parametrize("target", ["Half", "Float", "Double"])
@pytest.mark.parametrize("source", ["h", "f", "d", "i"])
def test_native_vector_conversion_matches_usd_save_reopen(tmp_path, dimension, target, source):
    value_type = getattr(Sdf.ValueTypeNames, f"{target}{dimension}")
    native_type = getattr(Gf, f"Vec{dimension}{source}")
    value = native_type(*range(1, dimension + 1))
    baseline = Usd.Stage.CreateInMemory()
    expected = baseline.DefinePrim("/World").CreateAttribute("test:value", value_type)
    # Let USD define the compatibility contract, rather than requiring an
    # exact Gf class or inventing our own cross-precision conversion policy.
    assert expected.Set(value, 1)

    path = str(tmp_path / "native.usda")
    create_stage(path)
    stage = Usd.Stage.Open(path)
    stage.GetPrimAtPath("/World").CreateAttribute("test:value", value_type)
    stage.GetRootLayer().Save()
    del stage
    author_attribute_samples(path, "/World", "test:value", [{"time": 1, "value": value}])
    reopened = Usd.Stage.Open(path)
    actual = reopened.GetPrimAtPath("/World").GetAttribute("test:value")
    assert actual.GetTypeName() == value_type
    assert actual.GetTimeSamples() == [1.0]
    assert actual.Get(1) == expected.Get(1)
    assert type(actual.Get(1)) is type(expected.Get(1))


@pytest.mark.parametrize("value", [[1, 2], [True, 1, 2], [float("nan"), 1, 2], [1e100, 1, 2]])
def test_invalid_json_after_native_vector_leaves_batch_unchanged(tmp_path, value):
    path = tmp_path / "mixed.usda"
    create_stage(str(path))
    stage = Usd.Stage.Open(str(path))
    attr = stage.GetPrimAtPath("/World").CreateAttribute("test:value", Sdf.ValueTypeNames.Float3)
    attr.Set(Gf.Vec3f(4, 5, 6), 0)
    stage.GetRootLayer().Save()
    before_file = path.read_bytes()
    before_layer = stage.GetRootLayer().ExportToString()
    with pytest.raises(OpenUsdError):
        author_attribute_samples(
            str(path),
            "/World",
            "test:value",
            [{"time": 1, "value": Gf.Vec3d(1, 2, 3)}, {"time": 2, "value": value}],
        )
    assert path.read_bytes() == before_file
    assert stage.GetRootLayer().ExportToString() == before_layer
    assert attr.GetTimeSamples() == [0.0]
    assert attr.Get(0) == Gf.Vec3f(4, 5, 6)


@pytest.mark.parametrize(
    "value", [[1], [1, 2, 3], [True, 1], ["0", 1], [float("nan"), 1], [float("inf"), 1], [1e100, 0]]
)
def test_invalid_vector_batch_leaves_file_unchanged(tmp_path, value):
    path = tmp_path / "invalid.usda"
    create_stage(str(path))
    stage = Usd.Stage.Open(str(path))
    stage.GetPrimAtPath("/World").CreateAttribute("test:value", Sdf.ValueTypeNames.Float2)
    stage.GetRootLayer().Save()
    before = path.read_bytes()
    with pytest.raises(OpenUsdError):
        author_attribute_samples(
            str(path), "/World", "test:value", [{"time": 1, "value": [0, 1]}, {"time": 2, "value": value}]
        )
    assert path.read_bytes() == before
    assert stage.GetPrimAtPath("/World").GetAttribute("test:value").GetTimeSamples() == []


def test_integer_vector_rejects_fractional_json_components(tmp_path):
    path = str(tmp_path / "integer.usda")
    create_stage(path)
    stage = Usd.Stage.Open(path)
    stage.GetPrimAtPath("/World").CreateAttribute("test:value", Sdf.ValueTypeNames.Int2)
    stage.GetRootLayer().Save()
    with pytest.raises(OpenUsdError, match="must be integers"):
        author_attribute_samples(path, "/World", "test:value", [{"time": 1, "value": [1.5, 2]}])


def test_nested_array_vectors_keep_existing_conversion(tmp_path):
    path = str(tmp_path / "curves.usda")
    create_stage(path)
    define_prim(path, "/World/Hair", "BasisCurves")
    values = [[0, 0, 0], [0, 0, 1], [0, 0, 2], [1, 0, 3]]
    author_attribute_samples(path, "/World/Hair", "points", [{"time": 1, "value": values}])
    stage = Usd.Stage.Open(path)
    assert [list(v) for v in stage.GetPrimAtPath("/World/Hair").GetAttribute("points").Get(1)] == values
