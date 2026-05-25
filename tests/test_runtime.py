from __future__ import annotations

import zipfile

from dcc_mcp_openusd.runtime import (
    add_reference,
    create_project,
    create_stage,
    define_xform,
    list_stage,
    package_usdz,
    snapshot_stage,
    validate_stage,
)


def test_create_project_creates_portable_layout(tmp_path):
    project = create_project(str(tmp_path / "coffee_shop"), name="Coffee Shop", up_axis="Z", meters_per_unit=0.01)

    project_dir = tmp_path / "coffee_shop"
    assert project_dir.joinpath("project.json").exists()
    assert project_dir.joinpath("scene.usda").exists()
    assert project_dir.joinpath("assets").is_dir()
    assert project["metadata"]["up_axis"] == "Z"


def test_stage_authoring_roundtrip(tmp_path):
    stage_file = tmp_path / "scene.usda"

    create_stage(str(stage_file), name="demo")
    define_xform(str(stage_file), "/World/Chair")
    add_reference(str(stage_file), "/World/Table", "assets/table.usda")

    listing = list_stage(str(stage_file))
    assert listing["prim_count"] >= 3
    assert any(prim["path"].endswith("Chair") for prim in listing["prims"])
    assert "assets/table.usda" in stage_file.read_text(encoding="utf-8")


def test_validation_and_package(tmp_path):
    stage_file = tmp_path / "scene.usda"
    package_file = tmp_path / "packages" / "scene.usdz"
    create_stage(str(stage_file), name="valid")

    validation = validate_stage(str(stage_file), strict=True)
    assert validation["valid"] is True

    packaged = package_usdz(str(stage_file), str(package_file))
    assert package_file.exists()
    assert packaged["package_file"] == str(package_file.resolve())
    with zipfile.ZipFile(package_file) as zf:
        assert "scene.usda" in zf.namelist()


def test_snapshot_stage(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="snap")

    result = snapshot_stage(str(stage_file), str(tmp_path / "snapshots"), name="review")

    assert result["snapshot_file"].endswith("review.usda")
    assert (tmp_path / "snapshots" / "review.usda").exists()
