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


def detect_runtime() -> RuntimeInfo:
    """Return optional Pixar USD runtime information."""
    try:
        from pxr import Usd  # type: ignore

        version = getattr(Usd, "GetVersion", lambda: None)()
        label = ".".join(str(part) for part in version) if version else None
        return RuntimeInfo(has_pxr=True, version=label)
    except Exception:
        return RuntimeInfo(has_pxr=False)


def create_project(
    project_dir: str, name: Optional[str] = None, up_axis: str = "Y", meters_per_unit: float = 1.0
) -> Dict[str, Any]:
    """Create a self-contained OpenUSD project folder."""
    root = Path(project_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for child in ("assets", "materials", "lights", "packages", "snapshots"):
        (root / child).mkdir(exist_ok=True)

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
    return {"project_dir": str(root), "stage_file": str(stage_path), "metadata": metadata}


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
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)
    if detect_runtime().has_pxr:
        try:
            from pxr import Usd  # type: ignore

            stage = Usd.Stage.Open(str(path))
            if stage is None:
                raise OpenUsdError(f"Could not open stage: {path}")
            prim = stage.DefinePrim(prim_path, "Xform")
            stage.GetRootLayer().Save()
            return {"stage_file": str(path), "prim_path": str(prim.GetPath()), "runtime": "pxr"}
        except Exception:
            pass

    text = path.read_text(encoding="utf-8")
    if prim_path in {prim["path"] for prim in _parse_prims_from_usda(text)}:
        return {"stage_file": str(path), "prim_path": prim_path, "created": False, "runtime": "text-fallback"}
    path.write_text(text.rstrip() + "\n\n" + _flat_prim_block(prim_path, "Xform") + "\n", encoding="utf-8")
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
    block = _flat_prim_block(prim_path, prim_type, reference=reference)
    path.write_text(text.rstrip() + "\n\n" + block + "\n", encoding="utf-8")
    return {"stage_file": str(path), "prim_path": prim_path, "asset_path": reference, "runtime": "text-fallback"}


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
    return {"stage_file": str(source), "snapshot_file": str(target)}


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


def _flat_prim_block(prim_path: str, prim_type: str, reference: Optional[str] = None) -> str:
    name = prim_path.rstrip("/").split("/")[-1]
    if reference:
        return f'def {prim_type} "{name}" (\n    prepend references = @{reference}@\n)\n{{\n}}'
    return f'def {prim_type} "{name}"\n{{\n}}'


def _parse_prims_from_usda(text: str) -> List[Dict[str, Any]]:
    prims: List[Dict[str, Any]] = []
    for match in re.finditer(r'\b(def|over|class)\s+([A-Za-z_][A-Za-z0-9_]*)\s+"([^"]+)"', text):
        name = match.group(3)
        prims.append({"path": f"/{name}", "type": match.group(2), "active": True})
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
