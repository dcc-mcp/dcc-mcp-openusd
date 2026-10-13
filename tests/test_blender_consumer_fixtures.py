"""Native validity controls for version-specific Blender consumer fixtures."""

from pathlib import Path

import pytest

pytest.importorskip("pxr")
from pxr import Gf, Usd, UsdGeom, UsdShade  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "blender_consumer"


def test_untyped_and_scope_parents_are_both_valid_native_instancers():
    stage = Usd.Stage.Open(str(FIXTURES / "pointinstancer.usda"))
    assert stage
    for name, expected_type, x in [
        ("UntypedContainer", "", -0.58),
        ("TypedScope", "Scope", 0.58),
    ]:
        parent = stage.GetPrimAtPath("/World/" + name)
        assert parent.IsDefined()
        assert parent.GetTypeName() == expected_type
        instancer = UsdGeom.PointInstancer.Get(stage, str(parent.GetPath()) + "/Instancer")
        prototypes = instancer.GetPrototypesRel().GetTargets()
        assert len(prototypes) == 2
        assert all(len(UsdGeom.Mesh.Get(stage, p).GetPointsAttr().Get()) == 4 for p in prototypes)
        assert list(instancer.GetProtoIndicesAttr().Get()) == [0, 1, 0]
        transforms = instancer.ComputeInstanceTransformsAtTime(Usd.TimeCode.Default(), Usd.TimeCode.Default())
        assert len(transforms) == 3
        for matrix, y in zip(transforms, [-0.55, 0, 0.55]):
            assert tuple(matrix.ExtractTranslation()) == pytest.approx((x, y, 0), abs=1e-6)
        # Asymmetric scale and 90-degree rotation cannot collapse into a count-only pass.
        transformed_x = transforms[1].TransformDir(Gf.Vec3d(1, 0, 0))
        assert tuple(transformed_x) == pytest.approx((0, 0.55, 0), abs=1e-3)
        assert tuple(transforms[2].TransformDir(Gf.Vec3d(0, 0, 1))) == pytest.approx((0, 0, 1.5))


def test_reader_fallback_is_authored_without_inventing_a_missing_primvar():
    stage = Usd.Stage.Open(str(FIXTURES / "material_fallback.usda"))
    assert stage
    reader = UsdShade.Shader.Get(stage, "/World/Reader/Reader")
    assert reader.GetIdAttr().Get() == "UsdPrimvarReader_float3"
    assert reader.GetInput("varname").Get() == "displayColor"
    fallback = tuple(reader.GetInput("fallback").Get())
    assert fallback == pytest.approx((0.08, 0.35, 0.025))
    present = UsdGeom.PrimvarsAPI(stage.GetPrimAtPath("/World/PresentPrimvar")).GetPrimvar("displayColor")
    absent = UsdGeom.PrimvarsAPI(stage.GetPrimAtPath("/World/AbsentPrimvarFallback")).GetPrimvar("displayColor")
    assert present.GetInterpolation() == "constant"
    assert tuple(present.Get()[0]) == pytest.approx(fallback)
    assert not absent or not absent.GetAttr().HasAuthoredValueOpinion()
    connected = UsdShade.Shader.Get(stage, "/World/Reader/Surface").GetInput("diffuseColor").GetConnectedSource()
    assert connected and connected[0].GetPrim() == reader.GetPrim()
