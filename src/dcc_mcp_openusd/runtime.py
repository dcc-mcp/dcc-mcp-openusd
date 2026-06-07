"""Small OpenUSD project helpers used by bundled skills.

The helpers prefer Pixar's ``pxr`` bindings when installed, but keep a safe
USDA text fallback so the adapter remains installable in lightweight agent and
CI environments.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


class OpenUsdError(RuntimeError):
    """Raised for user-facing OpenUSD tool failures."""


@dataclass
class RuntimeInfo:
    """Detected OpenUSD runtime availability."""

    has_pxr: bool
    version: Optional[str] = None


_RUNTIME_INFO: Optional[RuntimeInfo] = None


def detect_runtime() -> RuntimeInfo:
    """Return optional Pixar USD runtime information."""
    global _RUNTIME_INFO
    if _RUNTIME_INFO is not None:
        return _RUNTIME_INFO
    try:
        from pxr import Usd  # type: ignore

        version = getattr(Usd, "GetVersion", lambda: None)()
        label = ".".join(str(part) for part in version) if version else None
        _RUNTIME_INFO = RuntimeInfo(has_pxr=True, version=label)
    except Exception:
        _RUNTIME_INFO = RuntimeInfo(has_pxr=False)
    return _RUNTIME_INFO


def require_pxr(feature: str = "this operation") -> None:
    """Raise OpenUsdError when pxr is not installed.

    Guard complex authoring paths (UsdShade materials, UsdLux lights,
    UsdGeomCamera, time samples, variant/payload/sublayer edits) that
    cannot be expressed through text-fallback.
    """
    if not detect_runtime().has_pxr:
        raise OpenUsdError(f"{feature} requires the Pixar USD (pxr) package. Install it with: pip install usd-core")


def create_project(
    project_dir: str, name: Optional[str] = None, up_axis: str = "Y", meters_per_unit: float = 1.0
) -> Dict[str, Any]:
    """Create a self-contained OpenUSD project folder."""
    root = Path(project_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for child in ("assets", "materials", "lights", "packages", "snapshots"):
        (root / child).mkdir(exist_ok=True)

    runtime = detect_runtime()
    stage_path = root / "scene.usda"
    if not stage_path.exists():
        create_stage(str(stage_path), name=name or root.name, up_axis=up_axis, meters_per_unit=meters_per_unit)

    metadata = {
        "name": name or root.name,
        "created_at": int(time.time()),
        "stage_file": "scene.usda",
        "assets_dir": "assets",
        "materials_dir": "materials",
        "lights_dir": "lights",
        "packages_dir": "packages",
        "snapshots_dir": "snapshots",
        "up_axis": up_axis,
        "meters_per_unit": meters_per_unit,
    }
    (root / "project.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {
        "project_dir": str(root),
        "stage_file": str(stage_path),
        "metadata": metadata,
        "runtime": "pxr" if runtime.has_pxr else "text-fallback",
    }


def create_stage(
    stage_file: str, name: str = "scene", up_axis: str = "Y", meters_per_unit: float = 1.0
) -> Dict[str, Any]:
    """Create a minimal USD stage."""
    path = Path(stage_file).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    up_axis = _normalize_axis(up_axis)

    if detect_runtime().has_pxr:
        try:
            from pxr import Usd, UsdGeom  # type: ignore

            stage = Usd.Stage.CreateNew(str(path))
            UsdGeom.SetStageUpAxis(stage, up_axis)
            UsdGeom.SetStageMetersPerUnit(stage, float(meters_per_unit))
            world = stage.DefinePrim("/World", "Xform")
            stage.SetDefaultPrim(world)
            stage.GetRootLayer().Save()
            return {"stage_file": str(path), "default_prim": "World", "runtime": "pxr"}
        except Exception:
            pass

    path.write_text(_minimal_usda(name=name, up_axis=up_axis, meters_per_unit=meters_per_unit), encoding="utf-8")
    return {"stage_file": str(path), "default_prim": "World", "runtime": "text-fallback"}


def list_stage(stage_file: str) -> Dict[str, Any]:
    """List prims and basic stage metadata."""
    path = _existing_file(stage_file)
    if detect_runtime().has_pxr:
        try:
            from pxr import Usd  # type: ignore

            stage = Usd.Stage.Open(str(path))
            if stage is not None:
                prims = [
                    {"path": str(prim.GetPath()), "type": prim.GetTypeName(), "active": prim.IsActive()}
                    for prim in stage.Traverse()
                ]
                default_prim = stage.GetDefaultPrim()
                return {
                    "stage_file": str(path),
                    "prim_count": len(prims),
                    "prims": prims,
                    "default_prim": default_prim.GetName() if default_prim else None,
                    "runtime": "pxr",
                }
        except Exception:
            pass

    text = path.read_text(encoding="utf-8")
    prims = _parse_prims_from_usda(text)
    return {
        "stage_file": str(path),
        "prim_count": len(prims),
        "prims": prims,
        "default_prim": _find_default_prim(text),
        "runtime": "text-fallback",
    }


def define_xform(stage_file: str, prim_path: str) -> Dict[str, Any]:
    """Define an Xform prim."""
    return define_prim(stage_file, prim_path, "Xform")


def define_prim(stage_file: str, prim_path: str, prim_type: str = "Xform") -> Dict[str, Any]:
    """Define a prim with an arbitrary type name, preserving nested hierarchy."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)
    if detect_runtime().has_pxr:
        try:
            from pxr import Usd  # type: ignore

            stage = Usd.Stage.Open(str(path))
            if stage is None:
                raise OpenUsdError(f"Could not open stage: {path}")
            existing = stage.GetPrimAtPath(prim_path)
            created = not (existing and existing.IsValid())
            prim = stage.DefinePrim(prim_path, prim_type)
            stage.GetRootLayer().Save()
            return {"stage_file": str(path), "prim_path": str(prim.GetPath()), "runtime": "pxr", "created": created}
        except Exception:
            pass

    text = path.read_text(encoding="utf-8")
    existing_prims = {p["path"] for p in _parse_prims_from_usda(text)}
    if prim_path in existing_prims:
        return {"stage_file": str(path), "prim_path": prim_path, "created": False, "runtime": "text-fallback"}

    new_text = _insert_into_usda(text, prim_path, prim_type)
    path.write_text(new_text, encoding="utf-8")
    return {"stage_file": str(path), "prim_path": prim_path, "created": True, "runtime": "text-fallback"}


def add_reference(stage_file: str, prim_path: str, asset_path: str, prim_type: str = "Xform") -> Dict[str, Any]:
    """Define a prim that references another USD asset."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)
    asset = Path(asset_path).expanduser()
    reference = _relative_asset_path(path.parent, asset)
    if detect_runtime().has_pxr:
        try:
            from pxr import Usd  # type: ignore

            stage = Usd.Stage.Open(str(path))
            if stage is None:
                raise OpenUsdError(f"Could not open stage: {path}")
            prim = stage.DefinePrim(prim_path, prim_type)
            prim.GetReferences().AddReference(reference)
            stage.GetRootLayer().Save()
            return {
                "stage_file": str(path),
                "prim_path": str(prim.GetPath()),
                "asset_path": reference,
                "runtime": "pxr",
            }
        except Exception:
            pass

    text = path.read_text(encoding="utf-8")
    existing_prims = {p["path"] for p in _parse_prims_from_usda(text)}
    if prim_path in existing_prims:
        return {"stage_file": str(path), "prim_path": prim_path, "asset_path": reference, "runtime": "text-fallback"}

    new_text = _insert_into_usda(text, prim_path, prim_type, reference=reference)
    path.write_text(new_text, encoding="utf-8")
    return {"stage_file": str(path), "prim_path": prim_path, "asset_path": reference, "runtime": "text-fallback"}


def set_xform_ops(
    stage_file: str,
    prim_path: str,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Set transform operations on a prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    if detect_runtime().has_pxr:
        try:
            from pxr import Gf, Usd, UsdGeom  # type: ignore

            stage = Usd.Stage.Open(str(path))
            if stage is None:
                raise OpenUsdError(f"Could not open stage: {path}")
            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                raise OpenUsdError(f"Prim not found: {prim_path}")
            xform_api = UsdGeom.XformCommonAPI(prim)
            if translate is not None:
                xform_api.SetTranslate(Gf.Vec3d(*translate))
            if rotate is not None:
                xform_api.SetRotate(Gf.Vec3f(*rotate))
            if scale is not None:
                xform_api.SetScale(Gf.Vec3f(*scale))
            stage.GetRootLayer().Save()
            return {"stage_file": str(path), "prim_path": prim_path, "runtime": "pxr"}
        except Exception:
            pass

    # text-fallback: add xformOp attributes to the prim block
    text = path.read_text(encoding="utf-8")
    existing_prims = _parse_prims_from_usda(text)
    if prim_path not in {p["path"] for p in existing_prims}:
        raise OpenUsdError(f"Prim not found: {prim_path}")

    brace_pos = _find_prim_opening_brace(text, prim_path)
    if brace_pos is None:
        raise OpenUsdError(f"Prim not found: {prim_path}")

    parts_count = len(prim_path.strip("/").split("/"))
    indent = "    " * parts_count

    op_names = []
    xform_lines: List[str] = []
    if translate is not None:
        op_names.append('"xformOp:translate"')
        xform_lines.append(
            f"{indent}double3 xformOp:translate = ({translate[0]:g}, {translate[1]:g}, {translate[2]:g})"
        )
    if rotate is not None:
        op_names.append('"xformOp:rotateXYZ"')
        xform_lines.append(f"{indent}float3 xformOp:rotateXYZ = ({rotate[0]:g}, {rotate[1]:g}, {rotate[2]:g})")
    if scale is not None:
        op_names.append('"xformOp:scale"')
        xform_lines.append(f"{indent}float3 xformOp:scale = ({scale[0]:g}, {scale[1]:g}, {scale[2]:g})")

    if op_names:
        xform_lines.insert(0, f"{indent}uniform token[] xformOpOrder = [{', '.join(op_names)}]")

    if xform_lines:
        new_text = text[:brace_pos] + "\n" + "\n".join(xform_lines) + "\n" + text[brace_pos:]
        path.write_text(new_text, encoding="utf-8")

    return {"stage_file": str(path), "prim_path": prim_path, "runtime": "text-fallback"}


def set_stage_metadata(
    stage_file: str,
    up_axis: Optional[str] = None,
    meters_per_unit: Optional[float] = None,
    doc: Optional[str] = None,
    frames_per_second: Optional[float] = None,
) -> Dict[str, Any]:
    """Modify stage-level metadata (upAxis, metersPerUnit, doc, framesPerSecond)."""
    path = _existing_file(stage_file)

    if detect_runtime().has_pxr:
        try:
            from pxr import Usd, UsdGeom  # type: ignore

            stage = Usd.Stage.Open(str(path))
            if stage is None:
                raise OpenUsdError(f"Could not open stage: {path}")
            if up_axis is not None:
                UsdGeom.SetStageUpAxis(stage, _normalize_axis(up_axis))
            if meters_per_unit is not None:
                UsdGeom.SetStageMetersPerUnit(stage, float(meters_per_unit))
            if doc is not None:
                stage.SetMetadata("documentation", doc)
            if frames_per_second is not None:
                stage.SetMetadata("framesPerSecond", float(frames_per_second))
            stage.GetRootLayer().Save()
            return {"stage_file": str(path), "runtime": "pxr"}
        except Exception:
            pass

    # text-fallback: modify the metadata block in USDA text
    text = path.read_text(encoding="utf-8")
    runtime = "text-fallback"

    # Find the metadata block "( ... )" after "#usda 1.0"
    meta_match = re.search(r"(#usda\s+1\.0\s*\n\s*)\((.*?)\)", text, re.DOTALL)
    if not meta_match:
        return {"stage_file": str(path), "runtime": runtime}

    prefix = meta_match.group(1)
    inner = meta_match.group(2)

    def _set_meta(key: str, value_str: str) -> str:
        nonlocal inner
        if re.search(rf"^\s*{re.escape(key)}\s*=", inner, re.MULTILINE):
            inner = re.sub(rf"^(\s*{re.escape(key)}\s*=\s*).*$", rf"\g<1>{value_str}", inner, flags=re.MULTILINE)
        else:
            inner = inner.rstrip() + f"\n    {key} = {value_str}\n"
        return inner

    if up_axis is not None:
        _normalize_axis(up_axis)
        inner = _set_meta("upAxis", f'"{up_axis}"')
    if meters_per_unit is not None:
        inner = _set_meta("metersPerUnit", f"{float(meters_per_unit):g}")
    if doc is not None:
        inner = _set_meta("doc", f'"{doc}"')
    if frames_per_second is not None:
        inner = _set_meta("framesPerSecond", f"{float(frames_per_second):g}")

    new_text = text[: meta_match.start()] + f"{prefix}(\n{inner}\n)" + text[meta_match.end() :]
    path.write_text(new_text, encoding="utf-8")
    return {"stage_file": str(path), "runtime": runtime}


def validate_stage(stage_file: str, strict: bool = False) -> Dict[str, Any]:
    """Validate a stage using pxr when available plus adapter-level invariants."""
    path = _existing_file(stage_file)
    issues: List[Dict[str, str]] = []
    runtime = "text-fallback"

    if detect_runtime().has_pxr:
        try:
            from pxr import Usd  # type: ignore

            runtime = "pxr"
            stage = Usd.Stage.Open(str(path))
            if stage is None:
                issues.append({"severity": "error", "message": "Usd.Stage.Open returned None"})
            else:
                if not stage.GetDefaultPrim():
                    issues.append({"severity": "error", "message": "Stage has no defaultPrim"})
                if not any(True for _ in stage.Traverse()):
                    issues.append({"severity": "warning", "message": "Stage has no traversable prims"})
        except Exception as exc:
            issues.append({"severity": "error", "message": f"pxr validation failed: {exc}"})
    else:
        text = path.read_text(encoding="utf-8")
        if not text.lstrip().startswith("#usda"):
            issues.append({"severity": "error", "message": "Stage does not start with #usda"})
        if "defaultPrim" not in text:
            issues.append({"severity": "error", "message": "Stage has no defaultPrim metadata"})
        if "upAxis" not in text:
            issues.append({"severity": "warning", "message": "Stage has no upAxis metadata"})
        if strict and "metersPerUnit" not in text:
            issues.append({"severity": "error", "message": "Stage has no metersPerUnit metadata"})

    return {
        "stage_file": str(path),
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "issue_count": len(issues),
        "issues": issues,
        "runtime": runtime,
    }


def snapshot_stage(stage_file: str, output_dir: str, name: Optional[str] = None) -> Dict[str, Any]:
    """Copy a stage into a snapshots directory."""
    source = _existing_file(stage_file)
    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    label = _safe_name(name or f"{source.stem}-{int(time.time())}")
    target = target_dir / f"{label}{source.suffix or '.usda'}"
    shutil.copy2(source, target)
    runtime = detect_runtime()
    return {
        "stage_file": str(source),
        "snapshot_file": str(target),
        "runtime": "pxr" if runtime.has_pxr else "text-fallback",
    }


def package_usdz(stage_file: str, output_file: str) -> Dict[str, Any]:
    """Create a USDZ-style stored zip archive containing the root stage."""
    source = _existing_file(stage_file)
    target = Path(output_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if detect_runtime().has_pxr:
        try:
            from pxr import UsdUtils  # type: ignore

            ok = UsdUtils.CreateNewUsdzPackage(str(source), str(target))
            if ok:
                return {"stage_file": str(source), "package_file": str(target), "runtime": "pxr"}
        except Exception:
            pass

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.write(source, source.name)
    return {"stage_file": str(source), "package_file": str(target), "runtime": "text-fallback"}


# ── internal helpers ──


def _find_prim_opening_brace(text: str, prim_path: str) -> int | None:
    """Find the character position right after the opening brace of a prim by its full USDA path.

    Returns ``None`` when the prim is not found.
    """
    path_parts = [p for p in prim_path.strip("/").split("/") if p]
    if not path_parts:
        return None

    path_stack: List[str] = []
    for m in re.finditer(r'\b(?:def|over|class)\s+([A-Za-z_][A-Za-z0-9_]*)\s+"([^"]+)"', text):
        name = m.group(2)
        brace_depth = text[: m.start()].count("{") - text[: m.start()].count("}")
        while len(path_stack) > brace_depth:
            path_stack.pop()
        path_stack.append(name)
        if path_stack == path_parts:
            pos = m.end()
            while pos < len(text) and text[pos] != "{":
                pos += 1
            return pos + 1 if pos < len(text) else None

    return None


def _minimal_usda(name: str, up_axis: str, meters_per_unit: float) -> str:
    safe_name = _safe_name(name)
    return (
        "#usda 1.0\n"
        "(\n"
        '    defaultPrim = "World"\n'
        f"    metersPerUnit = {float(meters_per_unit):g}\n"
        f'    upAxis = "{up_axis}"\n'
        ")\n\n"
        'def Xform "World"\n'
        "{\n"
        f'    custom string dccMcpProjectName = "{safe_name}"\n'
        "}\n"
    )


def _build_nested_block(parts: List[str], prim_type: str, reference: Optional[str] = None) -> str:
    """Build a nested USDA def block from path segments.

    Intermediate ancestors always use ``Xform``; only the leaf receives *prim_type*.
    """
    lines: List[str] = []
    for i, part in enumerate(parts):
        indent = "    " * i
        is_leaf = i == len(parts) - 1
        node_type = prim_type if is_leaf else "Xform"
        if is_leaf and reference:
            lines.append(f'{indent}def {node_type} "{part}" (')
            lines.append(f"{indent}    prepend references = @{reference}@")
            lines.append(f"{indent})")
        else:
            lines.append(f'{indent}def {node_type} "{part}"')
        lines.append(f"{indent}{{")

    for i in range(len(parts) - 1, -1, -1):
        indent = "    " * i
        lines.append(f"{indent}}}")

    return "\n".join(lines)


def _insert_into_usda(text: str, prim_path: str, prim_type: str, reference: Optional[str] = None) -> str:
    """Insert a prim into USDA text at the correct hierarchy level."""
    parts = [p for p in prim_path.strip("/").split("/") if p]
    if not parts:
        raise OpenUsdError("prim_path must name a prim")

    existing = {p["path"] for p in _parse_prims_from_usda(text)}

    # Find the deepest existing parent
    existing_parent = ""
    for i in range(len(parts) - 1, -1, -1):
        candidate = "/" + "/".join(parts[: i + 1])
        if candidate in existing:
            existing_parent = candidate
            break

    if existing_parent:
        # Insert inside the existing parent
        parent_parts = existing_parent.strip("/").split("/")
        remaining = parts[len(parent_parts) :]
        if not remaining:
            return text  # Already exists
        block = _build_nested_block(remaining, prim_type, reference)
        return _insert_after_opening_brace(text, existing_parent, block)
    else:
        # No parent exists — append full nested block at end
        block = _build_nested_block(parts, prim_type, reference)
        return text.rstrip() + "\n\n" + block + "\n"


def _insert_after_opening_brace(text: str, parent_path: str, block: str) -> str:
    """Insert USDA block after the opening brace of the prim identified by *parent_path*."""
    brace_pos = _find_prim_opening_brace(text, parent_path)
    if brace_pos is None:
        return text.rstrip() + "\n\n" + block + "\n"

    parts_count = len(parent_path.strip("/").split("/"))
    indent = "    " * parts_count
    indented = "\n".join(indent + line for line in block.splitlines())
    return text[:brace_pos] + "\n" + indented + "\n" + text[brace_pos:]


def _parse_prims_from_usda(text: str) -> List[Dict[str, Any]]:
    """Parse prim definitions from USDA text, tracking nesting for correct paths."""
    prims: List[Dict[str, Any]] = []
    path_stack: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Match prim definition: def/over/class TypeName "name"
        match = re.match(r'\b(def|over|class)\s+([A-Za-z_][A-Za-z0-9_]*)\s+"([^"]+)"', stripped)
        if match:
            name = match.group(3)
            path_stack.append(name)
            full_path = "/" + "/".join(path_stack)
            prims.append({"path": full_path, "type": match.group(2), "active": True})

        # Track closing braces to pop the stack
        closes = stripped.count("}")
        for _ in range(closes):
            if path_stack:
                path_stack.pop()

    return prims


def _find_default_prim(text: str) -> Optional[str]:
    match = re.search(r'defaultPrim\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None


def _existing_file(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise OpenUsdError(f"Stage file does not exist: {resolved}")
    return resolved


def _normalize_axis(value: str) -> str:
    axis = value.upper()
    if axis not in {"X", "Y", "Z"}:
        raise OpenUsdError("up_axis must be X, Y, or Z")
    return axis


def _normalize_prim_path(value: str) -> str:
    if not value.startswith("/"):
        raise OpenUsdError("prim_path must be absolute, for example /World/Asset")
    if "//" in value or value == "/":
        raise OpenUsdError("prim_path must name a prim")
    return value


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    return cleaned or "openusd_project"


def _relative_asset_path(stage_dir: Path, asset: Path) -> str:
    try:
        return asset.resolve().relative_to(stage_dir.resolve()).as_posix()
    except Exception:
        return asset.as_posix()


# ---------------------------------------------------------------------------
# pxr-required helpers — fail fast without OpenUSD runtime
# ---------------------------------------------------------------------------

_MISSING_PXR_MESSAGE = "OpenUSD pxr runtime is required for this tool but is not available"


def _require_pxr() -> None:
    """Raise OpenUsdError when the Pixar USD runtime is missing."""
    if not detect_runtime().has_pxr:
        raise OpenUsdError(_MISSING_PXR_MESSAGE)


def _open_stage(path: Path):
    """Open an existing stage, failing fast on missing pxr or bad stage."""
    _require_pxr()
    from pxr import Usd  # type: ignore

    stage = Usd.Stage.Open(str(path))
    if stage is None:
        raise OpenUsdError(f"Could not open stage: {path}")
    return stage


# --- openusd-material -------------------------------------------------------


def create_material(stage_file: str, prim_path: str) -> Dict[str, Any]:
    """Create a UsdShadeMaterial prim in the stage."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    from pxr import UsdShade  # type: ignore

    stage = _open_stage(path)
    material = UsdShade.Material.Define(stage, prim_path)
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "material_path": str(material.GetPath()),
        "runtime": "pxr",
    }


def create_preview_surface(
    stage_file: str,
    material_path: str,
    shader_path: Optional[str] = None,
    diffuse_color: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Create a UsdPreviewSurface shader and connect it to the material's surface output."""
    path = _existing_file(stage_file)
    material_path = _normalize_prim_path(material_path)

    from pxr import Sdf, UsdShade  # type: ignore

    stage = _open_stage(path)
    material = UsdShade.Material.Get(stage, material_path)
    if not material:
        raise OpenUsdError(f"Material not found: {material_path}")

    if shader_path is None:
        shader_path = f"{material_path}/Shader"
    shader_path = _normalize_prim_path(shader_path)

    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.CreateIdAttr("UsdPreviewSurface")
    if diffuse_color:
        color = tuple(float(c) for c in diffuse_color[:3])
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color)

    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "material_path": material_path,
        "shader_path": shader_path,
        "runtime": "pxr",
    }


def bind_material(stage_file: str, prim_path: str, material_path: str) -> Dict[str, Any]:
    """Bind a UsdShadeMaterial to a prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)
    material_path = _normalize_prim_path(material_path)

    from pxr import UsdShade  # type: ignore

    stage = _open_stage(path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise OpenUsdError(f"Prim not found: {prim_path}")
    material = UsdShade.Material.Get(stage, material_path)
    if not material:
        raise OpenUsdError(f"Material not found: {material_path}")

    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "material_path": material_path,
        "runtime": "pxr",
    }


# --- openusd-light-camera ---------------------------------------------------


def create_camera(
    stage_file: str,
    prim_path: str,
    focal_length: float = 50.0,
    focus_distance: float = 100.0,
    f_stop: float = 2.8,
) -> Dict[str, Any]:
    """Create a UsdGeomCamera prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    from pxr import UsdGeom  # type: ignore

    stage = _open_stage(path)
    camera = UsdGeom.Camera.Define(stage, prim_path)
    camera.CreateFocalLengthAttr().Set(float(focal_length))
    camera.CreateFocusDistanceAttr().Set(float(focus_distance))
    camera.CreateFStopAttr().Set(float(f_stop))
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "runtime": "pxr",
    }


def create_distant_light(
    stage_file: str,
    prim_path: str,
    angle: float = 0.53,
    intensity: float = 1.0,
    color: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Create a DistantLight prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    from pxr import Gf, UsdLux  # type: ignore

    stage = _open_stage(path)
    light = UsdLux.DistantLight.Define(stage, prim_path)
    light.CreateAngleAttr().Set(float(angle))
    light.CreateIntensityAttr().Set(float(intensity))
    if color:
        light.CreateColorAttr().Set(Gf.Vec3f(*[float(c) for c in color[:3]]))
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "runtime": "pxr",
    }


def create_sphere_light(
    stage_file: str,
    prim_path: str,
    radius: float = 1.0,
    intensity: float = 1.0,
    color: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Create a SphereLight prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    from pxr import Gf, UsdLux  # type: ignore

    stage = _open_stage(path)
    light = UsdLux.SphereLight.Define(stage, prim_path)
    light.CreateRadiusAttr().Set(float(radius))
    light.CreateIntensityAttr().Set(float(intensity))
    if color:
        light.CreateColorAttr().Set(Gf.Vec3f(*[float(c) for c in color[:3]]))
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "runtime": "pxr",
    }


def set_transform(
    stage_file: str,
    prim_path: str,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Set translate, rotate (XYZ euler), and/or scale on an Xformable prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    from pxr import Gf, UsdGeom  # type: ignore

    stage = _open_stage(path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise OpenUsdError(f"Prim not found: {prim_path}")

    xform = UsdGeom.Xformable(prim)
    if translate:
        xform.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in translate[:3]]))
    if rotate:
        xform.AddRotateXYZOp().Set(Gf.Vec3f(*[float(v) for v in rotate[:3]]))
    if scale:
        xform.AddScaleOp().Set(Gf.Vec3f(*[float(v) for v in scale[:3]]))
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "runtime": "pxr",
    }


# --- openusd-animation ------------------------------------------------------


def set_time_codes(
    stage_file: str,
    start_time_code: float = 1.0,
    end_time_code: float = 120.0,
    frames_per_second: float = 24.0,
) -> Dict[str, Any]:
    """Set the time range and frame rate on a stage."""
    path = _existing_file(stage_file)

    stage = _open_stage(path)
    stage.SetStartTimeCode(float(start_time_code))
    stage.SetEndTimeCode(float(end_time_code))
    stage.SetTimeCodesPerSecond(float(frames_per_second))
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "start_time_code": float(start_time_code),
        "end_time_code": float(end_time_code),
        "frames_per_second": float(frames_per_second),
        "runtime": "pxr",
    }


def author_xform_samples(
    stage_file: str,
    prim_path: str,
    samples: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Write translate/rotate/scale time samples on an Xformable prim.

    ``samples`` is a list of dicts::

        [
            {"time": 1.0, "translate": [0,0,0], "rotate": [0,0,0], "scale": [1,1,1]},
            {"time": 24.0, "translate": [10,0,0], ...},
        ]
    """
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    from pxr import Gf, UsdGeom  # type: ignore

    stage = _open_stage(path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise OpenUsdError(f"Prim not found: {prim_path}")

    xform = UsdGeom.Xformable(prim)
    translate_op = xform.AddTranslateOp()
    rotate_op = xform.AddRotateXYZOp()
    scale_op = xform.AddScaleOp()

    for entry in samples:
        t = float(entry["time"])
        if "translate" in entry:
            v = entry["translate"]
            translate_op.Set(Gf.Vec3d(*[float(c) for c in v[:3]]), t)
        if "rotate" in entry:
            v = entry["rotate"]
            rotate_op.Set(Gf.Vec3f(*[float(c) for c in v[:3]]), t)
        if "scale" in entry:
            v = entry["scale"]
            scale_op.Set(Gf.Vec3f(*[float(c) for c in v[:3]]), t)

    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "sample_count": len(samples),
        "runtime": "pxr",
    }


def author_attribute_samples(
    stage_file: str,
    prim_path: str,
    attribute_name: str,
    samples: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Write time samples on an arbitrary attribute.

    ``samples`` is a list of dicts::

        [
            {"time": 1.0, "value": 0.5},
            {"time": 24.0, "value": 1.0},
        ]
    """
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    from pxr import Sdf  # type: ignore

    stage = _open_stage(path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise OpenUsdError(f"Prim not found: {prim_path}")

    attr = prim.GetAttribute(attribute_name)
    if not attr:
        attr = prim.CreateAttribute(attribute_name, Sdf.ValueTypeNames.Float)

    for entry in samples:
        t = float(entry["time"])
        attr.Set(entry["value"], t)

    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "attribute_name": attribute_name,
        "sample_count": len(samples),
        "runtime": "pxr",
    }


# --- openusd-composition ----------------------------------------------------


def add_sublayer(stage_file: str, sublayer_path: str, position: Optional[int] = None) -> Dict[str, Any]:
    """Add a sublayer to the stage's root layer."""
    path = _existing_file(stage_file)
    sublayer = Path(sublayer_path).expanduser()

    stage = _open_stage(path)
    root_layer = stage.GetRootLayer()
    sublayer_ref = _relative_asset_path(path.parent, sublayer)
    if position is not None:
        root_layer.subLayerPaths.insert(position, sublayer_ref)
    else:
        root_layer.subLayerPaths.append(sublayer_ref)
    root_layer.Save()
    return {
        "stage_file": str(path),
        "sublayer_path": sublayer_ref,
        "position": position if position is not None else len(root_layer.subLayerPaths) - 1,
        "runtime": "pxr",
    }


def add_payload(stage_file: str, prim_path: str, payload_path: str) -> Dict[str, Any]:
    """Add a payload arc on a prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)
    payload = Path(payload_path).expanduser()

    stage = _open_stage(path)
    prim = stage.DefinePrim(prim_path, "Xform")
    payload_ref = _relative_asset_path(path.parent, payload)
    prim.GetPayloads().AddPayload(payload_ref)
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "payload_path": payload_ref,
        "runtime": "pxr",
    }


def add_variant_set(stage_file: str, prim_path: str, variant_set_name: str) -> Dict[str, Any]:
    """Create a variant set on a prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    stage = _open_stage(path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise OpenUsdError(f"Prim not found: {prim_path}")
    prim.GetVariantSets().AddVariantSet(variant_set_name)
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "variant_set_name": variant_set_name,
        "runtime": "pxr",
    }


def set_variant_selection(
    stage_file: str, prim_path: str, variant_set_name: str, variant_name: str
) -> Dict[str, Any]:
    """Set the active variant selection for a variant set on a prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    stage = _open_stage(path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise OpenUsdError(f"Prim not found: {prim_path}")
    variant_set = prim.GetVariantSets().GetVariantSet(variant_set_name)
    variant_set.SetVariantSelection(variant_name)
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "variant_set_name": variant_set_name,
        "variant_name": variant_name,
        "runtime": "pxr",
    }
