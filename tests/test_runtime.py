from __future__ import annotations

import zipfile

from dcc_mcp_openusd.runtime import (
    OpenUsdError,
    _build_nested_block,
    _insert_into_usda,
    _parse_prims_from_usda,
    add_reference,
    create_project,
    create_stage,
    define_prim,
    define_xform,
    detect_runtime,
    list_stage,
    package_usdz,
    require_pxr,
    set_stage_metadata,
    set_xform_ops,
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
    assert "runtime" in project


def test_stage_authoring_roundtrip(tmp_path):
    stage_file = tmp_path / "scene.usda"

    create_stage(str(stage_file), name="demo")
    define_xform(str(stage_file), "/World/Chair")
    add_reference(str(stage_file), "/World/Table", "assets/table.usda")

    listing = list_stage(str(stage_file))
    assert listing["prim_count"] >= 3
    assert any(prim["path"].endswith("Chair") for prim in listing["prims"])
    assert "assets/table.usda" in stage_file.read_text(encoding="utf-8")
    assert "runtime" in listing


def test_hierarchy_preserved_text_fallback(tmp_path):
    """define_xform('/World/Chair/LegA') must retain the full path, not collapse to /LegA."""
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="hierarchy")

    result = define_xform(str(stage_file), "/World/Chair/LegA")
    assert result["created"] is True
    assert result["runtime"] in ("pxr", "text-fallback")

    listing = list_stage(str(stage_file))
    paths = {p["path"] for p in listing["prims"]}
    assert "/World" in paths
    assert "/World/Chair" in paths
    assert "/World/Chair/LegA" in paths
    # The old bug would produce /LegA (flat, without hierarchy)
    assert "/LegA" not in paths


def test_define_prim_arbitrary_type(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="types")

    result = define_prim(str(stage_file), "/World/Light", "SphereLight")
    assert result["created"] is True
    assert "runtime" in result

    listing = list_stage(str(stage_file))
    light_prim = next((p for p in listing["prims"] if p["path"] == "/World/Light"), None)
    assert light_prim is not None
    assert light_prim["type"] == "SphereLight"


def test_define_prim_idempotent(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="idem")

    first = define_prim(str(stage_file), "/World/Hero", "Mesh")
    assert first["created"] is True

    second = define_prim(str(stage_file), "/World/Hero", "Mesh")
    assert second["created"] is False


def test_set_xform_ops_text_fallback(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="xform")

    define_xform(str(stage_file), "/World/Cube")
    result = set_xform_ops(
        str(stage_file),
        "/World/Cube",
        translate=[1.0, 2.0, 3.0],
        rotate=[0.0, 90.0, 0.0],
        scale=[2.0, 2.0, 2.0],
    )
    assert result["runtime"] in ("pxr", "text-fallback")

    content = stage_file.read_text(encoding="utf-8")
    assert "xformOp:translate" in content
    assert "xformOp:rotateXYZ" in content
    assert "xformOp:scale" in content
    assert "xformOpOrder" in content


def test_set_xform_ops_prim_not_found_raises(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="xform")

    try:
        set_xform_ops(str(stage_file), "/World/Missing", translate=[1, 0, 0])
    except OpenUsdError as exc:
        assert "Prim not found" in str(exc)
    else:
        raise AssertionError("Expected OpenUsdError")


def test_set_stage_metadata_text_fallback(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="meta")

    result = set_stage_metadata(
        str(stage_file),
        up_axis="Z",
        meters_per_unit=0.01,
        doc="Test stage for metadata",
        frames_per_second=24.0,
    )
    assert result["runtime"] in ("pxr", "text-fallback")

    content = stage_file.read_text(encoding="utf-8")
    assert 'upAxis = "Z"' in content
    assert "metersPerUnit = 0.01" in content
    assert 'doc = "Test stage for metadata"' in content
    assert "framesPerSecond = 24" in content


def test_set_stage_metadata_partial_update(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="partial")

    # Only change up_axis, leave others as-is
    set_stage_metadata(str(stage_file), up_axis="X")

    content = stage_file.read_text(encoding="utf-8")
    assert 'upAxis = "X"' in content
    # Original metersPerUnit should still be there
    assert "metersPerUnit" in content


def test_require_pxr_guard():
    """require_pxr raises OpenUsdError when pxr is not available."""
    if detect_runtime().has_pxr:
        # pxr is available — guard should silently pass
        require_pxr("test operation")
    else:
        try:
            require_pxr("complex material authoring")
        except OpenUsdError as exc:
            assert "requires the Pixar USD (pxr) package" in str(exc)
        else:
            raise AssertionError("Expected OpenUsdError")


def test_all_runtime_fields_present(tmp_path):
    """Every public function must return a 'runtime' field."""
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="runtime-check")

    assert "runtime" in create_project(str(tmp_path / "proj"), name="test")
    assert "runtime" in snapshot_stage(str(stage_file), str(tmp_path / "snaps"))
    assert "runtime" in define_xform(str(stage_file), "/World/Test")
    assert "runtime" in define_prim(str(stage_file), "/World/Test2", "Xform")
    assert "runtime" in add_reference(str(stage_file), "/World/Ref", "assets/ref.usda")
    assert "runtime" in set_stage_metadata(str(stage_file), up_axis="Y")
    assert "runtime" in validate_stage(str(stage_file))
    assert "runtime" in package_usdz(str(stage_file), str(tmp_path / "out.usdz"))
    assert "runtime" in list_stage(str(stage_file))


def test_validation_and_package(tmp_path):
    stage_file = tmp_path / "scene.usda"
    package_file = tmp_path / "packages" / "scene.usdz"
    create_stage(str(stage_file), name="valid")

    validation = validate_stage(str(stage_file), strict=True)
    assert validation["valid"] is True
    assert "runtime" in validation

    packaged = package_usdz(str(stage_file), str(package_file))
    assert package_file.exists()
    assert packaged["package_file"] == str(package_file.resolve())
    assert "runtime" in packaged
    with zipfile.ZipFile(package_file) as zf:
        assert "scene.usda" in zf.namelist()


def test_snapshot_stage(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="snap")

    result = snapshot_stage(str(stage_file), str(tmp_path / "snapshots"), name="review")

    assert result["snapshot_file"].endswith("review.usda")
    assert "runtime" in result
    assert (tmp_path / "snapshots" / "review.usda").exists()


# ── internal helper tests ──


def test_parse_prims_tracks_nesting():
    usda = (
        "#usda 1.0\n"
        "(\n"
        '    defaultPrim = "World"\n'
        ")\n\n"
        'def Xform "World"\n'
        "{\n"
        '    def Xform "Chair"\n'
        "    {\n"
        '        def Xform "LegA"\n'
        "        {\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    prims = _parse_prims_from_usda(usda)
    paths = {p["path"] for p in prims}
    assert "/World" in paths
    assert "/World/Chair" in paths
    assert "/World/Chair/LegA" in paths
    # Old parser would produce /LegA (flat)
    assert "/LegA" not in paths


def test_parse_prims_handles_single_line_brace():
    usda = 'def Xform "World"\n{\n}\n'
    prims = _parse_prims_from_usda(usda)
    assert len(prims) == 1
    assert prims[0]["path"] == "/World"


def test_build_nested_block_single():
    block = _build_nested_block(["Chair"], "Xform")
    assert 'def Xform "Chair"' in block
    assert block.count("def") == 1


def test_build_nested_block_multi_level():
    block = _build_nested_block(["World", "Chair", "LegA"], "Xform")
    assert 'def Xform "World"' in block
    assert 'def Xform "Chair"' in block
    assert 'def Xform "LegA"' in block
    assert block.count("def") == 3
    # Check indentation
    lines = block.splitlines()
    assert lines[0] == 'def Xform "World"'
    assert lines[2] == '    def Xform "Chair"'
    assert lines[4] == '        def Xform "LegA"'


def test_build_nested_block_with_reference():
    block = _build_nested_block(["World", "Table"], "Xform", reference="assets/table.usda")
    assert "references" in block
    assert "@assets/table.usda@" in block
    # Reference should only appear on the leaf (Table), not the root (World)
    world_line = next(line for line in block.splitlines() if "World" in line)
    assert "references" not in world_line


def test_insert_into_usda_new_path(tmp_path):
    """Insert a new prim path into USDA with an existing parent."""
    usda_base = '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\ndef Xform "World"\n{\n}\n'
    result = _insert_into_usda(usda_base, "/World/Chair", "Xform")
    prims = _parse_prims_from_usda(result)
    paths = {p["path"] for p in prims}
    assert "/World" in paths
    assert "/World/Chair" in paths


def test_insert_into_usda_no_parent(tmp_path):
    """Insert a prim when no parent exists — full nested block appended."""
    usda_base = '#usda 1.0\n(\n    defaultPrim = "World"\n)\n\ndef Xform "World"\n{\n}\n'
    result = _insert_into_usda(usda_base, "/Foo/Bar", "Xform")
    prims = _parse_prims_from_usda(result)
    paths = {p["path"] for p in prims}
    assert "/Foo" in paths
    assert "/Foo/Bar" in paths


def test_set_xform_ops_none_present_raises(tmp_path):
    """set_xform_ops on missing prim must raise, not silently succeed."""
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file))

    try:
        set_xform_ops(str(stage_file), "/World/Nope", translate=[0, 0, 0])
    except OpenUsdError:
        pass
    else:
        raise AssertionError("Expected OpenUsdError for missing prim")
