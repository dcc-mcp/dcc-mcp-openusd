"""Small OpenUSD project helpers used by bundled skills.

The helpers prefer Pixar's ``pxr`` bindings when installed, but keep a safe
USDA text fallback so the adapter remains installable in lightweight agent and
CI environments.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from dcc_mcp_core.asset_import import AssetDescriptor, ImportToSceneRequest, ImportToSceneResult


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


# ---------------------------------------------------------------------------
# Stage validation
# ---------------------------------------------------------------------------

#: Stable validation rule codes. ``PIP-788`` owns the final ``ValidationIssue``
#: schema; this map is the code registry that schema will consume. The same rule
#: set is applied by both the pxr and the text-fallback runtime.
VALIDATION_RULES: Dict[str, str] = {
    "INVALID_STAGE_HEADER": "Text USD layer must start with a #usda header",
    "BINARY_LAYER_REQUIRES_PXR": "Binary USD layer can only be validated with the pxr package",
    "STAGE_OPEN_FAILED": "Stage could not be opened",
    "MISSING_DEFAULT_PRIM": "Stage does not declare defaultPrim",
    "INVALID_DEFAULT_PRIM": "defaultPrim does not resolve to an existing prim",
    "MISSING_UP_AXIS": "Stage does not declare upAxis",
    "INVALID_UP_AXIS": "upAxis must be one of X, Y, Z",
    "UP_AXIS_MISMATCH": "Sublayer declares a different upAxis than the root layer",
    "MISSING_METERS_PER_UNIT": "Stage does not declare metersPerUnit",
    "INVALID_METERS_PER_UNIT": "metersPerUnit must be a positive number",
    "METERS_PER_UNIT_MISMATCH": "Sublayer declares a different metersPerUnit than the root layer",
    "UNRESOLVED_REFERENCE": "Reference asset path cannot be resolved on disk",
    "REFERENCE_CYCLE": "Reference chain loops back to an already visited layer",
    "INCOMPLETE_MATERIAL": "Material has no surface output or shader",
    "DANGLING_MATERIAL_BINDING": "material:binding targets a missing or non-Material prim",
    "UNBOUND_MATERIAL": "Material is defined but never bound to any prim",
    "NO_TRAVERSABLE_PRIMS": "Stage has no traversable prims",
    "UNDEFINED_PRIM_TYPE": "Nested prim is defined without a type name",
}

#: Fix skill that can act on a rule code. Only codes with a real, offline-
#: testable fix skill are listed; everything else falls back to written guidance.
_FIX_SKILL_BY_CODE: Dict[str, str] = {
    "UNRESOLVED_REFERENCE": "openusd_stage__fix_reference_path",
    "DANGLING_MATERIAL_BINDING": "openusd_material__suggest_material_bind",
    "UNBOUND_MATERIAL": "openusd_material__suggest_material_bind",
}

#: Written recovery guidance for every rule. The three codes that have a fix
#: skill are listed as well: they are the fallback used when no stage path is
#: available to build ``suggested_fix`` args from, so ``next_steps`` stays
#: non-empty for every rule instead of depending on the caller.
_GUIDANCE_BY_CODE: Dict[str, str] = {
    "UNRESOLVED_REFERENCE": "Repair the reference asset path or point it at a file that exists",
    "DANGLING_MATERIAL_BINDING": "Rebind the prim to a Material that exists",
    "UNBOUND_MATERIAL": "Bind the material to a prim, or delete the material",
    "INVALID_STAGE_HEADER": "Add a '#usda 1.0' header line to the layer",
    "BINARY_LAYER_REQUIRES_PXR": "Install usd-core, then re-run validate_stage",
    "STAGE_OPEN_FAILED": "Repair or replace the layer that cannot be opened",
    "MISSING_DEFAULT_PRIM": "Set defaultPrim in the root layer metadata",
    "INVALID_DEFAULT_PRIM": "Point defaultPrim at a prim that exists",
    "MISSING_UP_AXIS": "Set upAxis in the root layer metadata",
    "INVALID_UP_AXIS": "Set upAxis to one of X, Y, or Z",
    "UP_AXIS_MISMATCH": "Align the sublayer upAxis with the root layer",
    "MISSING_METERS_PER_UNIT": "Set metersPerUnit in the root layer metadata",
    "INVALID_METERS_PER_UNIT": "Set metersPerUnit to a positive number",
    "METERS_PER_UNIT_MISMATCH": "Align the sublayer metersPerUnit with the root layer",
    "REFERENCE_CYCLE": "Break the reference loop between the listed layers",
    "INCOMPLETE_MATERIAL": "Add a UsdPreviewSurface shader and connect it to outputs:surface",
    "NO_TRAVERSABLE_PRIMS": "Author at least one prim in the stage",
    "UNDEFINED_PRIM_TYPE": 'Give the prim a type name, e.g. def Xform "Name"',
}

_RULE_SEVERITY: Dict[str, str] = {
    "INVALID_STAGE_HEADER": "error",
    "BINARY_LAYER_REQUIRES_PXR": "error",
    "STAGE_OPEN_FAILED": "error",
    "MISSING_DEFAULT_PRIM": "error",
    "INVALID_DEFAULT_PRIM": "error",
    "MISSING_UP_AXIS": "warning",
    "INVALID_UP_AXIS": "error",
    "UP_AXIS_MISMATCH": "error",
    "MISSING_METERS_PER_UNIT": "warning",
    "INVALID_METERS_PER_UNIT": "error",
    "METERS_PER_UNIT_MISMATCH": "error",
    "UNRESOLVED_REFERENCE": "error",
    "REFERENCE_CYCLE": "error",
    "INCOMPLETE_MATERIAL": "warning",
    "DANGLING_MATERIAL_BINDING": "error",
    "UNBOUND_MATERIAL": "warning",
    "NO_TRAVERSABLE_PRIMS": "warning",
    "UNDEFINED_PRIM_TYPE": "warning",
}

#: Rules that a strict run promotes from warning to error.
_STRICT_ERROR_RULES = frozenset({"MISSING_UP_AXIS", "MISSING_METERS_PER_UNIT"})

_VALID_AXES = ("X", "Y", "Z")
_MAX_LAYER_WALK = 16


@dataclass
class _StageFacts:
    """Runtime-independent facts collected from a stage before validation.

    Both the pxr and the text-fallback collector fill the same fields so that a
    single rule set can judge either runtime.
    """

    stage_path: Optional[Path] = None
    layer_chain: List[Dict[str, Any]] = field(default_factory=list)
    header_ok: bool = False
    binary_layer: bool = False
    open_error: Optional[str] = None
    prim_types: Dict[str, str] = field(default_factory=dict)
    untyped_prims: Set[str] = field(default_factory=set)
    materials: Dict[str, bool] = field(default_factory=dict)
    bindings: List[Tuple[str, str]] = field(default_factory=list)
    references: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def stage_dir(self) -> Path:
        """Directory that relative asset paths resolve against."""
        return self.stage_path.parent if self.stage_path else Path(".")


def validate_stage(stage_file: str, strict: bool = False) -> Dict[str, Any]:
    """Validate a stage using pxr when available plus adapter-level invariants.

    The rule set is shared by both runtimes. ``pxr`` is only used to extract
    composition facts (prim tree, references, material bindings); layer metadata
    and every rule itself run through the same code, so a stage is judged by the
    same rules whether or not ``pxr`` is installed.

    Every issue carries ``severity``, ``message``, plus a stable ``code`` from
    :data:`VALIDATION_RULES` and a ``location`` (prim path or ``[...]`` layer
    marker).
    """
    path = _existing_file(stage_file)
    facts, runtime = _collect_stage_facts(path)
    issues = _run_validators(facts, strict)
    return {
        "stage_file": str(path),
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "issue_count": len(issues),
        "issues": issues,
        "runtime": runtime,
        "rules": sorted(VALIDATION_RULES),
    }


def _collect_stage_facts(path: Path) -> Tuple[_StageFacts, str]:
    """Collect stage facts with the best runtime available.

    Shared by :func:`validate_stage` and the fix helpers so a fix operates on
    exactly the facts the validator judged, whichever runtime produced them.

    Returns the facts and the runtime label ("pxr" or "text-fallback").
    """
    chain = _collect_layer_chain(path)
    root_meta = chain[0] if chain else {}

    facts = _StageFacts(
        stage_path=path,
        layer_chain=chain,
        header_ok=bool(root_meta.get("header_ok")),
        binary_layer=bool(root_meta.get("binary")),
    )

    runtime = "text-fallback"
    if detect_runtime().has_pxr:
        try:
            facts = _collect_facts_pxr(path, chain)
            runtime = "pxr"
        except ImportError:
            # pxr is reported as available but not importable here; degrade to text.
            if not facts.binary_layer:
                facts = _collect_facts_text(path, chain)
        except Exception as exc:
            facts.open_error = str(exc)
            runtime = "pxr"
    elif not facts.binary_layer:
        # A binary layer is unreadable without pxr; BINARY_LAYER_REQUIRES_PXR reports it.
        facts = _collect_facts_text(path, chain)
    return facts, runtime


def _collect_facts_pxr(path: Path, chain: List[Dict[str, Any]]) -> _StageFacts:
    """Collect root-layer facts through the Pixar USD bindings.

    The walk is deliberately limited to the prim specs *authored in the root
    layer*. ``Usd.Stage.Traverse()`` would additionally report prims composed in
    from references and sublayers, which the text-fallback collector cannot see;
    restricting both collectors to the root layer is what keeps their facts
    equivalent. Because every asset path is then authored in the root layer,
    they are all resolved against the root layer's directory.
    """
    from pxr import Sdf  # type: ignore

    facts = _StageFacts(stage_path=path, layer_chain=chain)
    facts.header_ok = bool(chain and chain[0].get("header_ok"))
    facts.binary_layer = bool(chain and chain[0].get("binary"))

    layer = Sdf.Layer.FindOrOpen(str(path))
    if layer is None:
        raise OpenUsdError(f"Could not open stage: {path}")

    for spec, prim_path, descendants in _walk_layer_prim_specs(layer):
        prim_type = spec.typeName or ""
        # Several specs can collapse onto one path (the same prim name authored
        # in two variants), so merge rather than overwrite.
        facts.prim_types[prim_path] = _merge_prim_type(facts.prim_types.get(prim_path), prim_type)
        if spec.specifier == Sdf.SpecifierDef and not prim_type:
            facts.untyped_prims.add(prim_path)
        if prim_type == "Material":
            complete = "outputs:surface" in spec.properties or any(child.typeName == "Shader" for child in descendants)
            facts.materials[prim_path] = facts.materials.get(prim_path, False) or complete
        for asset in _spec_composition_assets(spec):
            facts.references.append((prim_path, asset))
        for name, property_spec in spec.properties.items():
            if not _is_material_binding_name(str(name)):
                continue
            targets = getattr(property_spec, "targetPathList", None)
            if targets is None:
                continue
            for target in targets.GetAppliedItems():
                facts.bindings.append((prim_path, _strip_property_suffix(str(target))))

    return facts


def _merge_prim_type(existing: Optional[str], new: str) -> str:
    """Fold a prim type into one already recorded for the same path.

    A prim name authored in several variants collapses onto a single flat path,
    so the value kept is the first non-empty type name rather than the last one
    seen, which would otherwise discard a real type in favour of an empty one.
    """
    if existing is None or (not existing and new):
        return new
    return existing


def _walk_layer_prim_specs(layer: Any) -> List[Tuple[Any, str, List[Any]]]:
    """Return ``(spec, flat_path, all_descendant_specs)`` for every prim spec.

    Pre-order depth first, so the ordering matches a textual scan of the file.

    Variant content is walked too, at the flat path it composes to: a Material
    authored inside ``variantSet "shading"`` under ``/Root/Looks`` is reported
    as ``/Root/Looks/RedMat``, which is both what the text collector's flat
    regex produces and what USD composes once the variant is selected. All
    variants are reported, not just the selected one, so a binding never looks
    dangling merely because it points into an unselected variant.
    """
    ordered: List[Tuple[Any, str, List[Any]]] = []

    def child_specs(spec: Any) -> List[Any]:
        """Name children plus the prim specs of every variant of every set."""
        children = list(spec.nameChildren)
        try:
            variant_sets = spec.variantSets
        except Exception:
            return children
        for set_name in variant_sets.keys():
            variant_set = variant_sets[set_name]
            for variant_name in variant_set.variants.keys():
                variant_prim = variant_set.variants[variant_name].primSpec
                if variant_prim is not None:
                    children.extend(variant_prim.nameChildren)
        return children

    def visit(spec: Any, path: str) -> List[Any]:
        """Record *spec* pre-order and return every descendant spec, full depth."""
        descendants: List[Any] = []
        ordered.append((spec, path, descendants))
        for child in child_specs(spec):
            descendants.append(child)
            descendants.extend(visit(child, path + "/" + child.name))
        return descendants

    for root in layer.rootPrims:
        visit(root, "/" + root.name)
    return ordered


def _spec_composition_assets(spec: Any) -> List[str]:
    """Return reference/payload asset paths authored on a prim spec."""
    assets: List[str] = []
    for list_editor in (spec.referenceList, spec.payloadList):
        try:
            items = list(list_editor.GetAppliedItems())
        except Exception:
            try:
                items = list(list_editor.GetAddedOrExplicitItems())
            except Exception:
                items = []
        for item in items:
            asset = getattr(item, "assetPath", "") or ""
            if asset:
                assets.append(asset)
    return assets


def _collect_facts_text(path: Path, chain: List[Dict[str, Any]]) -> _StageFacts:
    """Collect root-layer facts by parsing USDA text.

    Mirrors :func:`_collect_facts_pxr`: only the prims authored in this file are
    reported, and asset paths are resolved against this file's directory.
    """
    facts = _StageFacts(stage_path=path, layer_chain=chain)
    facts.header_ok = bool(chain and chain[0].get("header_ok"))
    facts.binary_layer = bool(chain and chain[0].get("binary"))
    if facts.binary_layer:
        return facts

    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = _parse_usda_blocks(text)
    for block in blocks:
        prim_path = block["path"]
        # Same merge as the pxr collector: a name authored in several variants
        # collapses onto one flat path.
        facts.prim_types[prim_path] = _merge_prim_type(facts.prim_types.get(prim_path), block["type"])
        if block["specifier"] == "def" and not block["type"]:
            facts.untyped_prims.add(prim_path)
        own_text = block["own_text"]
        if block["type"] == "Material":
            complete = _material_has_surface_text(prim_path, own_text, blocks)
            facts.materials[prim_path] = facts.materials.get(prim_path, False) or complete
        for asset in _find_reference_paths(own_text):
            facts.references.append((prim_path, asset))
        for target in _find_binding_targets(own_text):
            facts.bindings.append((prim_path, _strip_property_suffix(target)))
    return facts


def _material_has_surface_text(material_path: str, own_text: str, blocks: List[Dict[str, Any]]) -> bool:
    """Return True when a USDA Material prim has a surface output or a shader."""
    if re.search(r"\boutputs:surface\b", own_text):
        return True
    prefix = material_path + "/"
    return any(block["path"].startswith(prefix) and block["type"] == "Shader" for block in blocks)


def _is_material_binding_name(name: str) -> bool:
    """Return True for ``material:binding`` and its per-purpose variants.

    ``material:binding:collection:<name>`` is excluded: it targets a collection,
    not a material, so it must not be treated as a material binding. Both
    collectors share this filter so pxr and the text fallback agree.
    """
    if name == "material:binding":
        return True
    return name.startswith("material:binding:") and not name.startswith("material:binding:collection")


def _run_validators(facts: _StageFacts, strict: bool) -> List[Dict[str, Any]]:
    """Apply the shared rule set to collected stage facts."""
    issues: List[Dict[str, Any]] = []
    stage_file = str(facts.stage_path) if facts.stage_path else ""

    def next_steps_for(code: str, **fix_args: Optional[str]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return ``(suggested_fix, next_steps)`` for one issue.

        The ``suggested_fix`` shape is deliberately minimal
        (``{"skill": ..., "args": {...}}``) because the final
        ``ValidationIssue`` schema is owned by a separate change and will
        replace it in one pass. Rules with no fix skill still get a
        ``next_steps`` entry so the caller is never left without guidance.
        """
        skill = _FIX_SKILL_BY_CODE.get(code)
        if skill and stage_file:
            args: Dict[str, Any] = {"stage_file": stage_file}
            args.update({key: value for key, value in fix_args.items() if value})
            return {"skill": skill, "args": args}, [{"action": skill, "args": dict(args)}]
        guidance = _GUIDANCE_BY_CODE.get(code)
        if not guidance:
            return None, []
        return None, [{"action": "manual_fix", "detail": guidance}]

    def add(code: str, message: str, location: str = "/", **fix_args: Optional[str]) -> None:
        suggested_fix, next_steps = next_steps_for(code, **fix_args)
        issues.append(
            {
                "code": code,
                "severity": "error" if strict and code in _STRICT_ERROR_RULES else _RULE_SEVERITY[code],
                "message": message,
                "location": location,
                "suggested_fix": suggested_fix,
                "next_steps": next_steps,
            }
        )

    chain = facts.layer_chain
    root_meta = chain[0] if chain else {}
    stage_name = Path(root_meta.get("file") or "stage").name

    # ── layer integrity ────────────────────────────────────────────────────
    if facts.open_error:
        add("STAGE_OPEN_FAILED", f"Stage could not be opened: {facts.open_error}", f"[{stage_name}]")
    if facts.binary_layer:
        add(
            "BINARY_LAYER_REQUIRES_PXR",
            "Binary USD layer cannot be validated without the pxr package",
            f"[{stage_name}]",
        )
    elif not facts.header_ok:
        add("INVALID_STAGE_HEADER", "Stage does not start with a #usda header", "[line 1]")

    # ── defaultPrim ────────────────────────────────────────────────────────
    default_prim = root_meta.get("default_prim")
    if not default_prim:
        add("MISSING_DEFAULT_PRIM", "Stage has no defaultPrim metadata", f"[{stage_name}]")
    else:
        target = default_prim if str(default_prim).startswith("/") else "/" + str(default_prim)
        if target not in facts.prim_types:
            add(
                "INVALID_DEFAULT_PRIM",
                f"Stage defaultPrim '{default_prim}' does not resolve to an existing prim",
                target,
            )

    # ── units and up axis ──────────────────────────────────────────────────
    up_axis = root_meta.get("up_axis")
    if not up_axis:
        add("MISSING_UP_AXIS", "Stage has no upAxis metadata", f"[{stage_name}]")
    elif str(up_axis).upper() not in _VALID_AXES:
        add("INVALID_UP_AXIS", f"Stage upAxis '{up_axis}' is not one of X, Y, Z", f"[{stage_name}]")

    meters_per_unit = root_meta.get("meters_per_unit")
    if meters_per_unit is None:
        add("MISSING_METERS_PER_UNIT", "Stage has no metersPerUnit metadata", f"[{stage_name}]")
    elif not isinstance(meters_per_unit, float) or not meters_per_unit > 0 or not math.isfinite(meters_per_unit):
        add(
            "INVALID_METERS_PER_UNIT",
            f"Stage metersPerUnit must be a positive number, got {meters_per_unit!r}",
            f"[{stage_name}]",
        )

    for entry in chain[1:]:
        if not entry.get("available"):
            continue
        layer_name = Path(entry["file"]).name
        sub_axis = entry.get("up_axis")
        if sub_axis and up_axis and str(sub_axis).upper() != str(up_axis).upper():
            add(
                "UP_AXIS_MISMATCH",
                f"Sublayer upAxis '{sub_axis}' does not match root layer upAxis '{up_axis}'",
                f"[{layer_name}]",
            )
        sub_meters = entry.get("meters_per_unit")
        if (
            isinstance(sub_meters, float)
            and isinstance(meters_per_unit, float)
            and not math.isclose(sub_meters, meters_per_unit, rel_tol=1e-6, abs_tol=1e-9)
        ):
            add(
                "METERS_PER_UNIT_MISMATCH",
                f"Sublayer metersPerUnit {sub_meters:g} does not match root layer metersPerUnit {meters_per_unit:g}",
                f"[{layer_name}]",
            )

    # ── composition: references ────────────────────────────────────────────
    for prim_path, asset in facts.references:
        if _is_dynamic_asset_path(asset):
            continue
        resolved = _resolve_asset_path(facts.stage_dir, asset)
        if not resolved.exists():
            add(
                "UNRESOLVED_REFERENCE",
                f"Reference '{asset}' cannot be resolved on disk",
                prim_path,
                prim_path=prim_path,
            )

    if facts.stage_path is not None:
        cycle = _detect_reference_cycle(facts.stage_path)
        if cycle:
            add("REFERENCE_CYCLE", f"Reference chain loops back to {cycle}", f"[{cycle}]")

    # ── materials ──────────────────────────────────────────────────────────
    bound_targets = {target for _, target in facts.bindings}
    for prim_path, target in facts.bindings:
        target_type = facts.prim_types.get(target)
        if target_type is None:
            add(
                "DANGLING_MATERIAL_BINDING",
                f"material:binding targets '{target}' which does not exist",
                prim_path,
                prim_path=prim_path,
            )
        elif target_type != "Material":
            add(
                "DANGLING_MATERIAL_BINDING",
                f"material:binding targets '{target}' which is a '{target_type or 'typeless'}' prim, not a Material",
                prim_path,
                prim_path=prim_path,
            )

    for material_path in sorted(facts.materials):
        if not facts.materials[material_path]:
            add(
                "INCOMPLETE_MATERIAL",
                f"Material '{material_path}' has no connected surface output or shader",
                material_path,
            )
        if material_path not in bound_targets:
            add(
                "UNBOUND_MATERIAL",
                f"Material '{material_path}' is not bound to any prim",
                material_path,
                material_path=material_path,
            )

    # ── hierarchy ──────────────────────────────────────────────────────────
    if not facts.prim_types:
        add("NO_TRAVERSABLE_PRIMS", "Stage has no traversable prims", "/")
    for prim_path in sorted(facts.untyped_prims):
        add("UNDEFINED_PRIM_TYPE", f"Prim '{prim_path}' is defined without a type name", prim_path)

    return issues


# ---------------------------------------------------------------------------
# Fix skills
# ---------------------------------------------------------------------------

#: Maximum directory depth :func:`fix_reference_path` descends while searching
#: an asset library, and the cap on candidates it reports.
_SEARCH_MAX_DEPTH = 4
_SEARCH_MAX_MATCHES = 10

#: Prim types a material may reasonably be bound to. ``Scope`` and the shader
#: prims are excluded: binding a Scope hides nothing and binding a Shader is a
#: composition error, so neither belongs in a bind suggestion.
_BINDABLE_PRIM_TYPES = frozenset(
    {
        "Xform",
        "Mesh",
        "Points",
        "Cube",
        "Sphere",
        "Cone",
        "Cylinder",
        "Capsule",
        "Card",
        "Plane",
        "Grid",
        "BasisCurves",
        "NurbsCurves",
        "NurbsPatch",
        "GeomSubset",
        "Volume",
    }
)


def find_unresolved_references(stage_file: str, prim_path: Optional[str] = None) -> Dict[str, Any]:
    """Return every root-layer reference that cannot be resolved on disk.

    Read-only companion of :func:`fix_reference_path`: it reports the same
    ``UNRESOLVED_REFERENCE`` facts :func:`validate_stage` reports, including the
    asset path, so a caller can search for a replacement without re-parsing.
    """
    path = _existing_file(stage_file)
    facts, runtime = _collect_stage_facts(path)
    return {
        "stage_file": str(path),
        "runtime": runtime,
        "count": len(_unresolved_reference_targets(facts, prim_path)),
        "unresolved": _unresolved_reference_targets(facts, prim_path),
    }


def fix_reference_path(
    stage_file: str,
    prim_path: Optional[str] = None,
    asset_path: Optional[str] = None,
    search_dirs: Optional[List[str]] = None,
    apply: bool = False,
) -> Dict[str, Any]:
    """Repair broken reference/payload asset paths in a stage.

    With ``apply=False`` (the default) the stage is left untouched and every
    target comes back with ``status="planned"`` (a replacement exists but was
    not written) or ``status="unresolved"`` (nothing usable was found). With
    ``apply=True`` a found replacement is authored into the layer and read back.

    A replacement comes from ``asset_path`` when given, otherwise from a
    basename search under ``search_dirs``. Nothing is ever reported as fixed
    without a replacement that exists on disk, and a rewrite that cannot be
    applied is reported as ``status="failed"`` rather than skipped.
    """
    path = _existing_file(stage_file)
    facts, runtime = _collect_stage_facts(path)

    targets = _unresolved_reference_targets(facts, prim_path)
    explicit = _resolve_replacement_asset(path.parent, asset_path) if asset_path else None

    if asset_path and explicit is None:
        detail = "asset_path '%s' does not exist on disk" % asset_path
        failed = [
            {"prim_path": prim_path or "", "asset_path": "", "status": "failed", "detail": detail, "candidates": []}
        ]
        return _fix_result(path, runtime, failed)

    if asset_path and len(targets) > 1:
        # The filter narrows the prim, not the reference: one prim can author
        # several broken references, and a single asset_path silently collapsing
        # them into one would drop a reference while still reading back fixed.
        detail = (
            "several broken references match this filter; one asset_path can only replace "
            "one of them, so narrow the filter to a single reference"
        )
        failed = [
            {
                "prim_path": target["prim_path"],
                "asset_path": target["asset_path"],
                "status": "failed",
                "detail": detail,
                "candidates": [],
            }
            for target in targets
        ]
        return _fix_result(path, runtime, failed)

    # Plan every replacement before writing any of them, so a collision can be
    # rejected without leaving a half-rewritten layer behind.
    planned: List[Dict[str, Any]] = []
    for target in targets:
        replacement = explicit
        candidates: List[str] = []
        if replacement is None and search_dirs:
            candidates = _search_asset_candidates(target["basename"], search_dirs)
            if candidates:
                replacement = Path(candidates[0])
        if replacement is None:
            planned.append(
                {
                    "prim_path": target["prim_path"],
                    "asset_path": target["asset_path"],
                    "status": "unresolved",
                    "detail": "no replacement found; pass asset_path or search_dirs",
                    "candidates": candidates,
                }
            )
            continue
        planned.append(
            {
                "target": target,
                "replacement": replacement,
                "candidates": candidates,
                "new_asset": _relative_asset_path(path.parent, replacement),
            }
        )

    collapse = _collapsing_replacement(planned)
    if collapse is not None:
        prim, new_asset = collapse
        detail = (
            "prim '%s' has several broken references that would all be rewritten to '%s'; "
            "give each one its own replacement" % (prim, new_asset)
        )
        failed = [
            {
                "prim_path": item["target"]["prim_path"],
                "asset_path": item["target"]["asset_path"],
                "status": "failed",
                "detail": detail,
                "candidates": item["candidates"],
            }
            for item in planned
            if item.get("status") != "unresolved"
        ]
        unresolved = [item for item in planned if item.get("status") == "unresolved"]
        return _fix_result(path, runtime, failed, unresolved)

    resolved_targets: List[Dict[str, Any]] = []
    for item in planned:
        if item.get("status") == "unresolved":
            resolved_targets.append(item)
            continue
        resolved_targets.append(
            _rewrite_reference(path, facts, item["target"], item["replacement"], item["candidates"], apply=apply)
        )

    applied = any(target["status"] == "fixed" for target in resolved_targets)
    unresolved_targets = [target for target in resolved_targets if target["status"] == "unresolved"]
    failed_targets = [target for target in resolved_targets if target["status"] == "failed"]
    # Verified means the whole call did what it claimed, not "at least one
    # target was written".
    verified = applied and not unresolved_targets and not failed_targets
    return {
        "stage_file": str(path),
        "runtime": runtime,
        "applied": applied,
        "targets": resolved_targets,
        "unresolved": [dict(target) for target in resolved_targets if target["status"] == "unresolved"],
        "failed": [dict(target) for target in resolved_targets if target["status"] == "failed"],
        "verified": verified,
    }


def suggest_material_bind(
    stage_file: str,
    prim_path: Optional[str] = None,
    material_path: Optional[str] = None,
    apply: bool = False,
) -> Dict[str, Any]:
    """Suggest -- and optionally apply -- material bindings for a stage.

    Suggestions cover the two material rules :func:`validate_stage` emits: a
    binding pointing at a missing or non-Material prim, and a Material that is
    defined but never bound. Each suggestion carries every candidate the stage
    actually offers, so the caller can pick one without a second call.

    With ``apply=True`` the binding is written through :func:`bind_material`,
    which needs the ``pxr`` runtime; without it the call fails instead of
    reporting success. There is no asset-library search: a suggestion is built
    only from materials and prims that already exist in the stage.
    """
    path = _existing_file(stage_file)
    facts, runtime = _collect_stage_facts(path)

    wanted_prim = _normalize_prim_path(prim_path) if prim_path else None
    wanted_material = _normalize_prim_path(material_path) if material_path else None

    materials = sorted(facts.materials)
    bound_targets = {target for _, target in facts.bindings}
    bound_prims = {source for source, _ in facts.bindings}
    bindable_prims = sorted(
        candidate
        for candidate, prim_type in facts.prim_types.items()
        if prim_type in _BINDABLE_PRIM_TYPES and candidate not in materials
    )

    suggestions = []
    if wanted_prim and wanted_material:
        suggestions.append(
            {
                "prim_path": wanted_prim,
                "material_path": wanted_material,
                "reason": "explicit_request",
                "detail": "Caller supplied both prim_path and material_path",
                "candidates": [wanted_material],
                "auto_bindable": True,
            }
        )
    else:
        for source, target in facts.bindings:
            if wanted_prim and source != wanted_prim:
                continue
            target_type = facts.prim_types.get(target)
            if target_type == "Material":
                continue
            candidates = _rank_by_name(materials, target)
            if target_type is None:
                reason = "dangling_material_binding"
                detail = "material:binding targets '%s' which does not exist" % target
            else:
                reason = "non_material_binding_target"
                detail = "material:binding targets '%s', a '%s' prim, not a Material" % (
                    target,
                    target_type or "typeless",
                )
            suggestions.append(
                {
                    "prim_path": source,
                    "material_path": candidates[0] if candidates else "",
                    "reason": reason,
                    "detail": detail,
                    "candidates": candidates,
                    "auto_bindable": bool(candidates),
                }
            )

        for material in materials:
            if wanted_material and material != wanted_material:
                continue
            if material in bound_targets:
                continue
            if wanted_prim and wanted_prim in bindable_prims:
                # The caller named the prim to fix, so bind the material to it
                # rather than to some other prim the caller did not ask about.
                candidates = [wanted_prim]
            else:
                open_prims = [candidate for candidate in bindable_prims if candidate not in bound_prims]
                candidates = _rank_by_name(open_prims or bindable_prims, material)
            suggestions.append(
                {
                    "prim_path": candidates[0] if candidates else "",
                    "material_path": material,
                    "reason": "unbound_material",
                    "detail": "Material '%s' is not bound to any prim" % material,
                    "candidates": candidates,
                    "auto_bindable": bool(candidates),
                }
            )

    result = {
        "stage_file": str(path),
        "runtime": runtime,
        "applied": False,
        "suggestions": suggestions,
        "unresolved": [dict(item) for item in suggestions if not item["candidates"]],
        "failed": [],
        "verified": False,
    }
    if not apply:
        return result

    if not wanted_prim or not wanted_material:
        result["failed"] = [
            {
                "prim_path": wanted_prim or "",
                "material_path": wanted_material or "",
                "status": "failed",
                "detail": "apply=true requires both prim_path and material_path",
                "candidates": [],
            }
        ]
        return result

    if not detect_runtime().has_pxr:
        result["failed"] = [
            {
                "prim_path": wanted_prim,
                "material_path": wanted_material,
                "status": "failed",
                "detail": (
                    "Applying a material binding requires the pxr runtime; "
                    "install usd-core or apply the suggestion manually"
                ),
                "candidates": [wanted_material],
            }
        ]
        return result

    bind_material(str(path), wanted_prim, wanted_material)
    after, _runtime = _collect_stage_facts(path)
    verified = (wanted_prim, wanted_material) in after.bindings
    result["applied"] = True
    result["verified"] = verified
    if not verified:
        result["failed"] = [
            {
                "prim_path": wanted_prim,
                "material_path": wanted_material,
                "status": "failed",
                "detail": "bind_material returned but the binding is not visible after re-reading the stage",
                "candidates": [wanted_material],
            }
        ]
    return result


def _fix_result(
    path: Path,
    runtime: str,
    failed: List[Dict[str, Any]],
    unresolved: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a :func:`fix_reference_path` result whose listed targets failed.

    *unresolved* targets are reported alongside the failures rather than being
    dropped: a collision on one prim says nothing about a target elsewhere that
    simply had no candidate, and silently omitting it would hide work that
    still needs doing.
    """
    kept_unresolved = list(unresolved or [])
    return {
        "stage_file": str(path),
        "runtime": runtime,
        "applied": False,
        "targets": list(failed) + kept_unresolved,
        "unresolved": kept_unresolved,
        "failed": list(failed),
        "verified": False,
    }


def _unresolved_reference_targets(facts: _StageFacts, prim_path: Optional[str]) -> List[Dict[str, Any]]:
    """Collect the unresolved reference facts *prim_path* selects (all when None)."""
    wanted = _normalize_prim_path(prim_path) if prim_path else None
    targets = []
    seen = set()
    for ref_prim, asset in facts.references:
        if _is_dynamic_asset_path(asset):
            continue
        if wanted is not None and ref_prim != wanted:
            continue
        resolved = _resolve_asset_path(facts.stage_dir, asset)
        if resolved.exists():
            continue
        key = (ref_prim, asset)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            {
                "prim_path": ref_prim,
                "asset_path": asset,
                "resolved_path": str(resolved),
                "basename": resolved.name,
            }
        )
    return targets


def _resolve_replacement_asset(stage_dir: Path, asset_path: str) -> Optional[Path]:
    """Resolve a caller-supplied replacement asset, or return ``None``.

    Relative paths are tried against the stage directory first and then the
    current directory, which is how an agent naturally reads a broken
    ``./assets/...`` reference. A path that does not exist yields ``None`` so
    the caller fails instead of authoring another broken path.
    """
    candidate = Path(asset_path).expanduser()
    if not candidate.is_absolute():
        relative_to_stage = (stage_dir / candidate).resolve()
        if relative_to_stage.is_file():
            return relative_to_stage
        candidate = candidate.resolve()
    else:
        candidate = candidate.resolve()
    return candidate if candidate.is_file() else None


def _search_asset_candidates(basename: str, search_dirs: List[str]) -> List[str]:
    """Find files named *basename* under *search_dirs*, shallowest first.

    The walk is bounded by :data:`_SEARCH_MAX_DEPTH` and
    :data:`_SEARCH_MAX_MATCHES` so an asset library cannot turn a fix into an
    unbounded scan.
    """
    if not basename:
        return []
    candidates = []
    seen = set()
    for raw_dir in search_dirs:
        root = Path(raw_dir).expanduser()
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(str(root)):
            try:
                depth = len(Path(dirpath).relative_to(root).parts)
            except ValueError:
                depth = 0
            if depth >= _SEARCH_MAX_DEPTH:
                dirnames[:] = []
            dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
            for name in sorted(filenames):
                if name != basename:
                    continue
                candidate = Path(dirpath) / name
                key = _layer_key(candidate)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(str(candidate))
                if len(candidates) >= _SEARCH_MAX_MATCHES:
                    return candidates
    return candidates


def _rewrite_reference(
    path: Path,
    facts: _StageFacts,
    target: Dict[str, Any],
    replacement: Path,
    candidates: List[str],
    *,
    apply: bool,
) -> Dict[str, Any]:
    """Author *replacement* over a broken reference and read the result back."""
    prim_path = target["prim_path"]
    old_asset = target["asset_path"]
    new_asset = _relative_asset_path(path.parent, replacement)
    entry = {
        "prim_path": prim_path,
        "asset_path": old_asset,
        "replacement": new_asset,
        "candidates": candidates or [str(replacement)],
    }

    if not apply:
        entry["status"] = "planned"
        entry["detail"] = "Replacement '%s' found; nothing written" % new_asset
        return entry

    if facts.binary_layer:
        entry["status"] = "failed"
        entry["detail"] = "Layer is binary; rewriting a reference requires the pxr runtime"
        return entry

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        entry["status"] = "failed"
        entry["detail"] = "Layer could not be read for rewriting: %s" % exc
        return entry

    new_text, replacements = _replace_reference_asset(text, prim_path, old_asset, new_asset)
    if replacements == 0:
        entry["status"] = "failed"
        entry["detail"] = "No reference to '%s' is authored on prim '%s'" % (old_asset, prim_path)
        return entry

    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        entry["status"] = "failed"
        entry["detail"] = "Layer could not be written: %s" % exc
        return entry

    after, _runtime = _collect_stage_facts(path)
    authored = (prim_path, new_asset) in after.references
    on_disk = _resolve_asset_path(after.stage_dir, new_asset).exists()
    entry["status"] = "fixed" if authored and on_disk else "failed"
    entry["replacements"] = replacements
    entry["verified"] = authored and on_disk
    if authored and on_disk:
        entry["detail"] = "Rewrote %d reference(s) to '%s'" % (replacements, new_asset)
    else:
        entry["detail"] = "Layer was written but the readback disagrees: authored=%s resolved_on_disk=%s" % (
            authored,
            on_disk,
        )
    return entry


def _collapsing_replacement(planned: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """Return the first ``(prim_path, replacement)`` that two planned targets share.

    Two broken references on one prim are two authorings. Rewriting both to one
    asset drops one of them, yet the readback would still find that asset on the
    prim and report both as fixed, so the collision is rejected instead. Returns
    ``None`` when no two targets collide.
    """
    seen: Set[Tuple[str, str]] = set()
    for item in planned:
        if item.get("status") == "unresolved":
            continue
        key = (item["target"]["prim_path"], item["new_asset"])
        if key in seen:
            return key
        seen.add(key)
    return None


def _replace_reference_asset(text: str, prim_path: str, old_asset: str, new_asset: str) -> Tuple[str, int]:
    """Replace *old_asset* with *new_asset* in the reference statements of one prim.

    Only spans the prim owns are rewritten, so a child prim that happens to
    reference the same broken path keeps its own authoring. Scanning runs on the
    comment-masked text so a commented-out reference is left alone. Returns
    ``(text, replacements)``; ``replacements == 0`` means the prim does not
    author *old_asset*, which callers must treat as a failure rather than a
    silent no-op.
    """
    masked = _mask_usda_comments(text)
    blocks = _parse_usda_blocks(masked)
    block = next((item for item in blocks if item["path"] == prim_path), None)
    if block is None:
        return text, 0
    spans = []
    for start, end in block["own_spans"]:
        # Scan the masked text so a commented-out reference is left alone;
        # masking preserves every offset, so spans still index into the original.
        for asset_start, asset_end, asset in _reference_asset_spans(masked[start:end]):
            if asset == old_asset:
                spans.append((start + asset_start, start + asset_end))
    if not spans:
        return text, 0
    result = text
    # Rewrite back to front so earlier offsets stay valid.
    for start, end in reversed(spans):
        result = result[:start] + "@" + new_asset + "@" + result[end:]
    return result, len(spans)


def _rank_by_name(candidates: List[str], wanted: str) -> List[str]:
    """Order *candidates* by how closely their prim name resembles *wanted*.

    A dangling binding to ``/World/Materials/MissingPropPaint`` ranks
    ``/World/Materials/PropPaint`` first, which is the suggestion a human would
    make; ties fall back to path order so the output stays deterministic.
    """
    wanted_name = wanted.rstrip("/").rsplit("/", 1)[-1].lower()

    def key(candidate):
        name = candidate.rstrip("/").rsplit("/", 1)[-1].lower()
        exact = 0 if name == wanted_name else 1
        partial = 0 if wanted_name and (wanted_name in name or name in wanted_name) else 1
        return (exact, partial, candidate)

    return sorted(candidates, key=key)


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
    """Return the USDA text of a minimal stage used by the text fallback."""
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
    """Return the defaultPrim name authored anywhere in USDA text."""
    match = re.search(r'defaultPrim\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# USDA text parsing helpers used by stage validation
# ---------------------------------------------------------------------------

_USDA_HEADER_RE = re.compile(r"^\s*#usda\s", re.MULTILINE)
_USDA_PRIM_RE = re.compile(r'\b(def|over|class)\s+(?:([A-Za-z_][A-Za-z0-9_:]*)\s+)?"([^"]+)"')
_ASSET_PATH_RE = re.compile(r"@([^@]*)@")
_REFERENCE_RE = re.compile(r"\b(?:(?:prepend|append|add)\s+)?(?:references|payload)\s*=")
_BINDING_RE = re.compile(r"\bmaterial:binding(?::[A-Za-z0-9_:]+)?\s*=\s*([^\n]*)")
_SUBLAYER_RE = re.compile(r"\bsubLayers\s*=")
_BINARY_MAGIC = b"PXR-USDC"


def _strip_usda_comments(text: str) -> str:
    """Remove ``#`` comments from USDA text, preserving line offsets.

    Quoted strings and ``@asset@`` paths are copied verbatim so asset paths
    containing ``#`` survive parsing.
    """
    out: List[str] = []
    quote: Optional[str] = None
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if quote:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            index += 1
            continue
        if char == "@":
            delimiter = "@@" if text.startswith("@@", index) else "@"
            end = text.find(delimiter, index + len(delimiter))
            if end == -1:
                out.append(text[index:])
                break
            out.append(text[index : end + len(delimiter)])
            index = end + len(delimiter)
            continue
        if char == "#" and not (index == 0 and text.startswith("#usda")):
            newline = text.find("\n", index)
            if newline == -1:
                break
            out.append("\n")
            index = newline + 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _mask_usda_comments(text: str) -> str:
    """Blank ``#`` comments in place, preserving every character offset.

    :func:`_strip_usda_comments` drops comment text and therefore renumbers
    character offsets, which makes it unusable for rewrite helpers. This
    variant replaces the comment body with spaces instead, so the block
    positions :func:`_parse_usda_blocks` reports stay valid against the
    original file. Newlines survive, so line numbers are unchanged too, and
    quoted strings and ``@asset@`` paths are left untouched.
    """
    chars = list(text)
    quote: Optional[str] = None
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if quote:
            if char == "\\" and index + 1 < length:
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'":
            quote = char
            index += 1
            continue
        if char == "@":
            delimiter = "@@" if text.startswith("@@", index) else "@"
            end = text.find(delimiter, index + len(delimiter))
            index = length if end == -1 else end + len(delimiter)
            continue
        if char == "#" and not (index == 0 and text.startswith("#usda")):
            newline = text.find("\n", index)
            stop = length if newline == -1 else newline
            for position in range(index, stop):
                chars[position] = " "
            index = length if newline == -1 else newline + 1
            continue
        index += 1
    return "".join(chars)


def _skip_usda_token(text: str, index: int) -> int:
    """Return the index just past the quoted string or asset path at *index*."""
    char = text[index]
    if char == "@":
        delimiter = "@@" if text.startswith("@@", index) else "@"
        end = text.find(delimiter, index + len(delimiter))
        return len(text) if end == -1 else end + len(delimiter)
    end = index + 1
    while end < len(text):
        if text[end] == "\\":
            end += 2
            continue
        if text[end] == char:
            return end + 1
        end += 1
    return len(text)


def _matching_delimiter(text: str, open_index: int, open_char: str, close_char: str) -> int:
    """Return the index of the delimiter closing the one at *open_index*, or -1.

    Delimiters inside quoted strings and ``@asset@`` paths are ignored, so
    dictionary values such as ``customData = { string a = ")" }`` or sublayer
    offsets such as ``[@./x.usda@ (offset = 1)]`` do not terminate the scan.
    """
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == '"' or char == "'" or char == "@":
            index = _skip_usda_token(text, index)
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _skip_prim_metadata(text: str, index: int) -> int:
    """Return *index* advanced past any balanced ``( ... )`` prim metadata.

    A prim header may carry dictionaries (``customData = { ... }``,
    ``assetInfo = { ... }``) inside its metadata block, so the body brace cannot
    be found by scanning for the first ``{``. Every balanced paren group at the
    start of the header is skipped first.
    """
    while index < len(text):
        probe = index
        while probe < len(text) and text[probe] in " \t\r\n":
            probe += 1
        if probe >= len(text) or text[probe] != "(":
            return index
        close = _matching_delimiter(text, probe, "(", ")")
        if close == -1:
            return index
        index = close + 1


_VARIANT_SET_RE = re.compile(r'\bvariantSet\s+"[^"]*"\s*=\s*\{')
_VARIANT_ENTRY_RE = re.compile(r'(?m)^[ \t]*"[^"]*"\s*\{')


def _variant_block_spans(text: str) -> List[Tuple[int, int]]:
    """Return spans of every variantSet block and every variant block in it.

    Both open a brace level that does not correspond to a prim, so path
    inference has to discount them.
    """
    spans: List[Tuple[int, int]] = []
    for match in _VARIANT_SET_RE.finditer(text):
        open_index = match.end() - 1
        close_index = _matching_delimiter(text, open_index, "{", "}")
        if close_index == -1:
            continue
        spans.append((match.start(), close_index))

        # Claim only the variant entries directly inside this block. Scanning
        # the whole body would also match the entries of any nested variantSet,
        # which then get claimed a second time when that nested set is visited
        # by _VARIANT_SET_RE, double-counting their brace level. Skipping past
        # each entry's own closing brace leaves nested blocks to their own match.
        index = open_index + 1
        while index < close_index:
            entry = _VARIANT_ENTRY_RE.search(text, index, close_index)
            if entry is None:
                break
            entry_open = entry.end() - 1
            entry_close = _matching_delimiter(text, entry_open, "{", "}")
            if entry_close == -1 or entry_close >= close_index:
                break
            spans.append((entry.start(), entry_close))
            index = entry_close + 1
    return spans


def _variant_depth_counts(text: str) -> List[int]:
    """Return, for every index, how many variant blocks enclose it."""
    delta = [0] * (len(text) + 2)
    for open_index, close_index in _variant_block_spans(text):
        delta[open_index] += 1
        delta[min(close_index + 1, len(text) + 1)] -= 1
    counts: List[int] = []
    running = 0
    for index in range(len(text) + 1):
        running += delta[index]
        counts.append(running)
    return counts


def _parse_usda_blocks(text: str) -> List[Dict[str, Any]]:
    """Parse USDA text into nested prim blocks.

    Each block carries the prim ``path``, ``type``, ``specifier``, ``line`` and
    ``own_text`` — the text owned by that prim (its metadata block plus its body
    with nested child blocks removed), so validators never attribute a child's
    references or bindings to its parent.
    """
    stripped = _strip_usda_comments(text)
    # Braces inside quoted strings and @asset@ paths are not nesting, so they
    # are skipped with the same token scanner _matching_delimiter() uses.
    # Positions are still recorded for skipped characters so that depth_at
    # stays index-aligned with the text.
    depth_at: List[int] = []
    depth = 0
    index = 0
    length = len(stripped)
    while index < length:
        char = stripped[index]
        if char == '"' or char == "'" or char == "@":
            skip_to = _skip_usda_token(stripped, index)
            depth_at.extend([depth] * (skip_to - index))
            index = skip_to
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        depth_at.append(depth)
        index += 1
    # variantSet blocks and their per-variant blocks are composition
    # scaffolding, not prim nesting, so their braces must not shift a prim's
    # inferred path. Without this the second and later variants of a prim are
    # nested under the first one instead of being flattened as pxr reports them.
    variant_depth = _variant_depth_counts(stripped)

    blocks: List[Dict[str, Any]] = []
    stack: List[str] = []
    for match in _USDA_PRIM_RE.finditer(stripped):
        start = match.start()
        brace_depth = depth_at[start - 1] if start else 0
        depth = max(0, brace_depth - variant_depth[start])
        del stack[depth:]
        name = match.group(3)
        path = "/" + "/".join(stack + [name])
        stack.append(name)

        header_end = _skip_prim_metadata(stripped, match.end())
        brace = stripped.find("{", header_end)
        if brace == -1:
            continue
        # A prim whose next sibling starts before any brace has no body.
        next_prim = _USDA_PRIM_RE.search(stripped, header_end)
        if next_prim is not None and next_prim.start() < brace:
            continue
        close = _matching_delimiter(stripped, brace, "{", "}")
        if close == -1:
            close = len(stripped)
        blocks.append(
            {
                "path": path,
                "parent": path.rsplit("/", 1)[0] or "/",
                "type": match.group(2) or "",
                "specifier": match.group(1),
                "line": stripped.count("\n", 0, start) + 1,
                "start": start,
                "brace": brace,
                "close": close,
            }
        )

    children_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    for block in blocks:
        children_by_parent.setdefault(block["parent"], []).append(block)

    for block in blocks:
        spans: List[Tuple[int, int]] = [(block["start"], block["brace"] + 1)]
        cursor = block["brace"] + 1
        for child in sorted(children_by_parent.get(block["path"], []), key=lambda item: item["start"]):
            if child["start"] >= cursor:
                spans.append((cursor, child["start"]))
                cursor = max(cursor, child["close"] + 1)
        spans.append((cursor, block["close"]))
        spans = [(start, end) for start, end in spans if end > start]
        block["own_spans"] = spans
        block["own_text"] = "".join(stripped[start:end] for start, end in spans)

    return blocks


def _parse_usda_metadata(text: str) -> Dict[str, Any]:
    """Read the layer metadata block of a USDA text layer."""
    stripped = _strip_usda_comments(text)
    info: Dict[str, Any] = {
        "header_ok": False,
        "default_prim": None,
        "up_axis": None,
        "meters_per_unit": None,
        "sublayers": [],
    }
    header = _USDA_HEADER_RE.search(stripped)
    if not header:
        return info
    info["header_ok"] = True

    open_index = stripped.find("(", header.end())
    if open_index == -1:
        return info

    # Match the closing paren instead of taking the first one: sublayer offsets
    # are written as [@./x.usda@ (offset = 1; scale = 2)], which contains its
    # own ')'. Quoted strings and asset paths are skipped while scanning.
    end = len(stripped)
    close_index = _matching_delimiter(stripped, open_index, "(", ")")
    if close_index != -1:
        end = min(end, close_index)
    first_prim = _USDA_PRIM_RE.search(stripped, open_index)
    if first_prim:
        end = min(end, first_prim.start())
    block = stripped[open_index + 1 : end]

    match = re.search(r'\bdefaultPrim\s*=\s*"([^"]+)"', block)
    if match:
        info["default_prim"] = match.group(1)
    match = re.search(r'\bupAxis\s*=\s*"([^"]+)"', block)
    if match:
        info["up_axis"] = match.group(1)
    match = re.search(r"\bmetersPerUnit\s*=\s*([-+0-9.eE]+)", block)
    if match:
        try:
            info["meters_per_unit"] = float(match.group(1))
        except ValueError:
            info["meters_per_unit"] = match.group(1)
    info["sublayers"] = _find_sublayer_assets(block)
    return info


def _find_sublayer_assets(block: str) -> List[str]:
    """Return every asset path in a ``subLayers`` statement.

    The list is matched across newlines so the common multi-line form is not
    silently reduced to an empty chain:

    .. code-block:: text

        subLayers = [
            @./sub_a.usda@,
            @./sub_b.usda@
        ]
    """
    match = _SUBLAYER_RE.search(block)
    if not match:
        return []
    index = match.end()
    while index < len(block) and block[index] in " \t":
        index += 1
    if index < len(block) and block[index] == "[":
        close = _matching_delimiter(block, index, "[", "]")
        segment = block[index:] if close == -1 else block[index : close + 1]
    else:
        newline = block.find("\n", index)
        segment = block[index:] if newline == -1 else block[index:newline]
    return [asset for asset in _ASSET_PATH_RE.findall(segment) if asset]


def _read_layer_metadata(path: Path) -> Dict[str, Any]:
    """Read layer-level metadata from a USD layer file.

    Text layers are parsed directly so the pxr and text-fallback runtimes agree;
    binary layers fall back to pxr when it is installed.
    """
    info: Dict[str, Any] = {
        "file": str(path),
        "available": False,
        "binary": False,
        "header_ok": False,
        "default_prim": None,
        "up_axis": None,
        "meters_per_unit": None,
        "sublayers": [],
    }
    try:
        raw = path.read_bytes()
    except OSError:
        return info

    info["available"] = True
    info["binary"] = raw[:8] == _BINARY_MAGIC
    if not info["binary"]:
        info.update(_parse_usda_metadata(raw.decode("utf-8", errors="replace")))
        return info

    if detect_runtime().has_pxr:
        try:
            from pxr import Sdf  # type: ignore

            layer = Sdf.Layer.FindOrOpen(str(path))
            if layer is not None:
                root = Sdf.Path.absoluteRootPath
                if layer.HasField(root, "upAxis"):
                    info["up_axis"] = str(layer.upAxis)
                if layer.HasField(root, "metersPerUnit"):
                    info["meters_per_unit"] = float(layer.metersPerUnit)
                if layer.HasField(root, "defaultPrim"):
                    info["default_prim"] = str(layer.defaultPrim)
                info["sublayers"] = [str(sub) for sub in layer.subLayerPaths]
                info["header_ok"] = True
        except Exception:
            pass
    return info


def _collect_layer_chain(root: Path, max_layers: int = _MAX_LAYER_WALK) -> List[Dict[str, Any]]:
    """Return the root layer metadata followed by every reachable sublayer."""
    chain: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    queue: List[Path] = [root]
    while queue and len(chain) < max_layers:
        current = queue.pop(0)
        key = _layer_key(current)
        if key in seen:
            continue
        seen.add(key)
        meta = _read_layer_metadata(current)
        chain.append(meta)
        for sublayer in meta["sublayers"]:
            queue.append(_resolve_asset_path(current.parent, sublayer))
    return chain


def _layer_key(path: Path) -> str:
    """Return a comparable identity for a layer file.

    ``os.path.normcase`` is used instead of a blanket ``.lower()`` so that
    case-sensitive filesystems keep ``Set.usda`` and ``set.usda`` apart.
    """
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def _resolve_asset_path(base_dir: Path, asset_path: str) -> Path:
    """Resolve a USD asset path against the directory of the layer that owns it."""
    candidate = asset_path.strip()
    if not candidate:
        return base_dir
    if re.match(r"^[A-Za-z]:[\\/]", candidate) or candidate.startswith(("/", "\\\\")):
        return Path(candidate)
    return base_dir / candidate


def _is_dynamic_asset_path(asset_path: str) -> bool:
    """Return True for patterns (UDIM, globs, URIs) that are not plain files."""
    candidate = asset_path.strip()
    if any(char in candidate for char in "<>*?"):
        return True
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://", candidate))


def _strip_property_suffix(target: str) -> str:
    """Drop the ``.property`` suffix from a relationship target path."""
    return target.split(".", 1)[0] or target


def _find_reference_paths(body: str) -> List[str]:
    """Return every asset path authored by a ``references``/``payload`` statement."""
    return [asset for _, _, asset in _reference_asset_spans(body)]


def _reference_asset_spans(body: str) -> List[Tuple[int, int, str]]:
    """Return ``(start, end, asset_path)`` for every reference/payload asset in *body*.

    The offsets cover the whole ``@...@`` token and are relative to *body*, so a
    rewrite helper can turn them into file offsets by adding the offset of the
    slice it passed in.
    """
    spans: List[Tuple[int, int, str]] = []
    for match in _REFERENCE_RE.finditer(body):
        index = match.end()
        depth = 0
        while index < len(body):
            char = body[index]
            if char == "[":
                depth += 1
            elif char == "]":
                depth = max(0, depth - 1)
            elif char == "\n" and depth == 0:
                break
            index += 1
        for asset_match in _ASSET_PATH_RE.finditer(body, match.end(), index):
            asset = asset_match.group(1)
            if asset:
                spans.append((asset_match.start(), asset_match.end(), asset))
    return spans


def _find_binding_targets(body: str) -> List[str]:
    """Return every target of a material binding relationship.

    Shares :func:`_is_material_binding_name` with the pxr collector so both
    runtimes accept the same set of relationship names.
    """
    targets: List[str] = []
    for match in _BINDING_RE.finditer(body):
        if not _is_material_binding_name(match.group(0).split("=")[0].strip()):
            continue
        targets.extend(re.findall(r"<([^>]+)>", match.group(1)))
    return targets


def _read_layer_references(path: Path) -> List[str]:
    """Return every asset path referenced or payloaded by a layer file."""
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if raw[:8] == _BINARY_MAGIC:
        return []
    return _find_reference_paths(_strip_usda_comments(raw.decode("utf-8", errors="replace")))


def _detect_reference_cycle(root: Path) -> Optional[str]:
    """Return the file name closing a reference cycle, or ``None``."""
    visited: Set[str] = set()
    stack: List[str] = []

    def walk(layer: Path, depth: int) -> Optional[str]:
        if depth > _MAX_LAYER_WALK:
            return None
        key = _layer_key(layer)
        if key in stack:
            return layer.name
        if key in visited:
            return None
        visited.add(key)
        stack.append(key)
        try:
            for asset in _read_layer_references(layer):
                if _is_dynamic_asset_path(asset):
                    continue
                found = walk(_resolve_asset_path(layer.parent, asset), depth + 1)
                if found:
                    return found
        finally:
            stack.pop()
        return None

    return walk(root, 0)


def _existing_file(path: str) -> Path:
    """Resolve *path* and raise OpenUsdError when it is not an existing file."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise OpenUsdError(f"Stage file does not exist: {resolved}")
    return resolved


def _normalize_axis(value: str) -> str:
    """Validate an up-axis token and return it upper-cased."""
    axis = value.upper()
    if axis not in {"X", "Y", "Z"}:
        raise OpenUsdError("up_axis must be X, Y, or Z")
    return axis


def _normalize_prim_path(value: str) -> str:
    """Validate an absolute Sdf prim path."""
    if not value.startswith("/"):
        raise OpenUsdError("prim_path must be absolute, for example /World/Asset")
    if "//" in value or value == "/":
        raise OpenUsdError("prim_path must name a prim")
    return value


def _safe_name(value: str) -> str:
    """Convert an arbitrary label into a USDA-safe identifier."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    return cleaned or "openusd_project"


def _relative_asset_path(stage_dir: Path, asset: Path) -> str:
    """Return *asset* relative to *stage_dir*, falling back to the absolute path."""
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


def _float3(values: List[float], name: str) -> tuple[float, float, float]:
    """Validate and normalize a three-component numeric value."""
    if len(values) != 3:
        raise OpenUsdError(f"{name} must contain exactly 3 numbers")
    return tuple(float(value) for value in values)


def _unit_float(value: float, name: str) -> float:
    """Validate a normalized scalar input."""
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise OpenUsdError(f"{name} must be between 0 and 1")
    return normalized


def create_points(
    stage_file: str,
    prim_path: str,
    positions: List[List[float]],
    widths: Optional[List[float]] = None,
    colors: Optional[List[List[float]]] = None,
    velocities: Optional[List[List[float]]] = None,
    ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Create a portable UsdGeom.Points FX primitive."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)
    point_count = len(positions)
    if point_count == 0:
        raise OpenUsdError("positions must contain at least one point")

    optional_values = {
        "widths": widths,
        "colors": colors,
        "velocities": velocities,
        "ids": ids,
    }
    for name, values in optional_values.items():
        if values is not None and len(values) != point_count:
            raise OpenUsdError(f"{name} must contain one value per point")

    stage = _open_stage(path)
    from pxr import Gf, UsdGeom, Vt  # type: ignore

    points = UsdGeom.Points.Define(stage, prim_path)
    points.CreatePointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*_float3(value, "position")) for value in positions]))
    if widths is not None:
        points.CreateWidthsAttr().Set(Vt.FloatArray([float(value) for value in widths]))
        points.SetWidthsInterpolation(UsdGeom.Tokens.vertex)
    if colors is not None:
        primvar = points.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex)
        primvar.Set(Vt.Vec3fArray([Gf.Vec3f(*_float3(value, "color")) for value in colors]))
    if velocities is not None:
        points.CreateVelocitiesAttr().Set(
            Vt.Vec3fArray([Gf.Vec3f(*_float3(value, "velocity")) for value in velocities])
        )
    if ids is not None:
        points.CreateIdsAttr().Set(Vt.Int64Array([int(value) for value in ids]))

    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "point_count": point_count,
        "runtime": "pxr",
    }


def create_mesh(
    stage_file: str,
    prim_path: str,
    points: List[List[float]],
    face_vertex_counts: List[int],
    face_vertex_indices: List[int],
    subdivision_scheme: str = "none",
    double_sided: bool = False,
) -> Dict[str, Any]:
    """Create renderer-neutral ``UsdGeom.Mesh`` polygon topology."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)
    if len(points) < 3:
        raise OpenUsdError("points must contain at least three positions")
    if not face_vertex_counts:
        raise OpenUsdError("face_vertex_counts must contain at least one face")

    counts = [int(value) for value in face_vertex_counts]
    if any(value < 3 for value in counts):
        raise OpenUsdError("every face_vertex_counts value must be at least 3")
    indices = [int(value) for value in face_vertex_indices]
    if sum(counts) != len(indices):
        raise OpenUsdError("sum of face_vertex_counts must equal the number of face_vertex_indices")
    if any(value < 0 or value >= len(points) for value in indices):
        raise OpenUsdError("face_vertex_indices contains an out-of-range point index")

    schemes = {"none": "none", "catmullClark": "catmullClark", "bilinear": "bilinear"}
    if subdivision_scheme not in schemes:
        raise OpenUsdError("subdivision_scheme must be one of: none, catmullClark, bilinear")

    stage = _open_stage(path)
    from pxr import Gf, UsdGeom, Vt  # type: ignore

    mesh = UsdGeom.Mesh.Define(stage, prim_path)
    point_values = Vt.Vec3fArray([Gf.Vec3f(*_float3(value, "point")) for value in points])
    mesh.CreatePointsAttr().Set(point_values)
    mesh.CreateFaceVertexCountsAttr().Set(Vt.IntArray(counts))
    mesh.CreateFaceVertexIndicesAttr().Set(Vt.IntArray(indices))
    mesh.CreateSubdivisionSchemeAttr().Set(getattr(UsdGeom.Tokens, schemes[subdivision_scheme]))
    mesh.CreateDoubleSidedAttr().Set(bool(double_sided))
    mesh.CreateExtentAttr().Set(UsdGeom.PointBased.ComputeExtent(point_values))

    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "point_count": len(points),
        "face_count": len(counts),
        "face_vertex_count": len(indices),
        "subdivision_scheme": subdivision_scheme,
        "runtime": "pxr",
    }


# --- openusd-material -------------------------------------------------------


def create_material(stage_file: str, prim_path: str) -> Dict[str, Any]:
    """Create a UsdShadeMaterial prim in the stage."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    stage = _open_stage(path)
    from pxr import UsdShade  # type: ignore

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
    metallic: Optional[float] = None,
    roughness: Optional[float] = None,
    emissive_color: Optional[List[float]] = None,
    opacity: Optional[float] = None,
    clearcoat: Optional[float] = None,
    clearcoat_roughness: Optional[float] = None,
    ior: Optional[float] = None,
) -> Dict[str, Any]:
    """Create a UsdPreviewSurface shader and connect it to the material's surface output."""
    path = _existing_file(stage_file)
    material_path = _normalize_prim_path(material_path)

    stage = _open_stage(path)
    from pxr import Sdf, UsdShade  # type: ignore

    material = UsdShade.Material.Get(stage, material_path)
    if not material:
        raise OpenUsdError(f"Material not found: {material_path}")

    if shader_path is None:
        shader_path = f"{material_path}/Shader"
    shader_path = _normalize_prim_path(shader_path)

    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.CreateIdAttr("UsdPreviewSurface")
    if diffuse_color is not None:
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(_float3(diffuse_color, "diffuse_color"))
    scalar_inputs = {
        "metallic": metallic,
        "roughness": roughness,
        "opacity": opacity,
        "clearcoat": clearcoat,
        "clearcoatRoughness": clearcoat_roughness,
    }
    for input_name, value in scalar_inputs.items():
        if value is not None:
            shader.CreateInput(input_name, Sdf.ValueTypeNames.Float).Set(_unit_float(value, input_name))
    if emissive_color is not None:
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(_float3(emissive_color, "emissive_color"))
    if ior is not None:
        ior_value = float(ior)
        if ior_value <= 0:
            raise OpenUsdError("ior must be greater than 0")
        shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(ior_value)

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

    stage = _open_stage(path)
    from pxr import UsdShade  # type: ignore

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

    stage = _open_stage(path)
    from pxr import UsdGeom  # type: ignore

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

    stage = _open_stage(path)
    from pxr import Gf, UsdLux  # type: ignore

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


def create_dome_light(
    stage_file: str,
    prim_path: str,
    texture_file: Optional[str] = None,
    intensity: float = 1.0,
    exposure: float = 0.0,
    color: Optional[List[float]] = None,
    texture_format: str = "latlong",
) -> Dict[str, Any]:
    """Create a DomeLight with an optional HDR environment texture."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)
    if texture_format not in {"automatic", "latlong", "mirroredBall", "angular", "cubeMapVerticalCross"}:
        raise OpenUsdError("texture_format is not a supported UsdLux dome texture format")

    stage = _open_stage(path)
    from pxr import Sdf, UsdLux  # type: ignore

    light = UsdLux.DomeLight.Define(stage, prim_path)
    light.CreateIntensityAttr().Set(float(intensity))
    light.CreateExposureAttr().Set(float(exposure))
    if color is not None:
        light.CreateColorAttr().Set(_float3(color, "color"))

    texture_ref = None
    if texture_file is not None:
        texture_path = Path(texture_file).expanduser()
        if not texture_path.is_file():
            raise OpenUsdError(f"Dome texture file does not exist: {texture_path.resolve()}")
        texture_ref = _relative_asset_path(path.parent, texture_path)
        light.CreateTextureFileAttr().Set(Sdf.AssetPath(texture_ref))
        light.CreateTextureFormatAttr().Set(texture_format)

    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "texture_file": texture_ref,
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

    stage = _open_stage(path)
    from pxr import Gf, UsdLux  # type: ignore

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

    stage = _open_stage(path)
    from pxr import Gf, UsdGeom  # type: ignore

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


def set_visibility(stage_file: str, prim_path: str, visible: bool = True) -> Dict[str, Any]:
    """Set authored visibility on an Imageable prim."""
    path = _existing_file(stage_file)
    prim_path = _normalize_prim_path(prim_path)

    stage = _open_stage(path)
    from pxr import UsdGeom  # type: ignore

    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise OpenUsdError(f"Prim not found: {prim_path}")

    imageable = UsdGeom.Imageable(prim)
    if not imageable:
        raise OpenUsdError(f"Prim is not Imageable: {prim_path}")
    visibility = UsdGeom.Tokens.inherited if visible else UsdGeom.Tokens.invisible
    imageable.CreateVisibilityAttr().Set(visibility)
    stage.GetRootLayer().Save()
    return {
        "stage_file": str(path),
        "prim_path": prim_path,
        "visibility": visibility,
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

    stage = _open_stage(path)
    from pxr import Gf, UsdGeom  # type: ignore

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

    stage = _open_stage(path)
    from pxr import Sdf  # type: ignore

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


def set_variant_selection(stage_file: str, prim_path: str, variant_set_name: str, variant_name: str) -> Dict[str, Any]:
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


# --- asset_import contract adapters -----------------------------------------


def asset_source(stage_file: str, asset_id: Optional[str] = None) -> "AssetDescriptor":
    """Expose a USD/USDZ stage as an AssetDescriptor for cross-DCC consumption.

    Reads stage metadata (upAxis, metersPerUnit) from the file when pxr is
    available; falls back to USDA text parsing otherwise.  The returned
    descriptor always has at least one ``AssetFileVariant`` pointing to the
    resolved stage file.

    Parameters
    ----------
    stage_file:
        Path to a ``.usd``, ``.usda``, ``.usdc``, or ``.usdz`` file.
    asset_id:
        Logical identifier for the asset.  Defaults to the stem of
        *stage_file* when not provided.

    Returns
    -------
    AssetDescriptor
        A populated contract object ready for other DCC adapters to consume.
    """
    from dcc_mcp_core.asset_import import (  # type: ignore
        AssetDescriptor,
        AssetFileVariant,
        AssetFormat,
        AxisHint,
        UnitHint,
    )

    path = _existing_file(stage_file)
    suffix = path.suffix.lower().lstrip(".")
    fmt = AssetFormat.USDZ if suffix == "usdz" else AssetFormat.USD

    resolved_id = asset_id or path.stem

    # Defaults — overridden by stage metadata when pxr is available
    up_axis = AxisHint.Y
    meters_per_unit = 1.0
    unit_hint = UnitHint.METER
    variant_sets: List[str] = []

    if detect_runtime().has_pxr:
        try:
            from pxr import Usd, UsdGeom  # type: ignore

            stage = Usd.Stage.Open(str(path))
            if stage is not None:
                raw_axis = UsdGeom.GetStageUpAxis(stage)
                up_axis = raw_axis.lower() if raw_axis else AxisHint.Y
                mpu = UsdGeom.GetStageMetersPerUnit(stage)
                if mpu:
                    meters_per_unit = float(mpu)
                    if abs(meters_per_unit - 1.0) < 1e-9:
                        unit_hint = UnitHint.METER
                    elif abs(meters_per_unit - 0.01) < 1e-9:
                        unit_hint = UnitHint.CENTIMETER
                    elif abs(meters_per_unit - 0.0254) < 1e-9:
                        unit_hint = UnitHint.INCH
                    else:
                        unit_hint = UnitHint.UNITLESS
                # Collect variant set names from the default prim
                default_prim = stage.GetDefaultPrim()
                if default_prim and default_prim.IsValid():
                    variant_sets = list(default_prim.GetVariantSets().GetNames())
        except Exception:
            pass
    elif fmt != AssetFormat.USDZ:
        # USDZ is a binary zip archive — skip text parsing
        text = path.read_text(encoding="utf-8")
        axis_match = re.search(r'upAxis\s*=\s*"([^"]+)"', text)
        if axis_match:
            up_axis = axis_match.group(1).lower()
        mpu_match = re.search(r"metersPerUnit\s*=\s*([0-9.e+-]+)", text)
        if mpu_match:
            try:
                meters_per_unit = float(mpu_match.group(1))
                if abs(meters_per_unit - 1.0) < 1e-9:
                    unit_hint = UnitHint.METER
                elif abs(meters_per_unit - 0.01) < 1e-9:
                    unit_hint = UnitHint.CENTIMETER
                elif abs(meters_per_unit - 0.0254) < 1e-9:
                    unit_hint = UnitHint.INCH
                else:
                    unit_hint = UnitHint.UNITLESS
            except ValueError:
                pass

    extra: Dict[str, Any] = {}
    if variant_sets:
        extra["variant_sets"] = variant_sets
    extra["composition_arcs"] = _detect_composition_arcs(path)

    variant = AssetFileVariant(
        local_path=str(path),
        format=fmt,
        preferred=True,
    )
    descriptor = AssetDescriptor(
        asset_id=resolved_id,
        variants=[variant],
        up_axis=up_axis,
        meters_per_unit=meters_per_unit,
        unit_hint=unit_hint,
        extra=extra,
    )
    descriptor.validate()
    return descriptor


def import_to_scene(
    stage_file: str,
    request: "ImportToSceneRequest",
    target_prim_path: Optional[str] = None,
) -> "ImportToSceneResult":
    """Import an asset described by *request* into a USD stage.

    Selects the preferred USD/USDZ variant from the descriptor and wires it
    into the stage using the most appropriate USD composition arc:

    - **reference** (default): standard asset assembly
    - **payload**: deferred loading for heavy assets (set
      ``request.extra["usd_arc"] = "payload"`` to activate)
    - **sublayer**: merge whole layers (set
      ``request.extra["usd_arc"] = "sublayer"``)

    Placement hints (translate/rotate/scale) are applied via
    ``UsdGeom.XformCommonAPI`` when pxr is available.

    Parameters
    ----------
    stage_file:
        The receiving USD stage file path.
    request:
        Populated ``ImportToSceneRequest`` from the asset_import contract.
    target_prim_path:
        Override the prim path in the stage.  Defaults to
        ``/World/<asset_id>``.

    Returns
    -------
    ImportToSceneResult
        Success flag, list of imported prim paths, and any non-fatal warnings.
    """
    from dcc_mcp_core.asset_import import (  # type: ignore
        AssetFormat,
        ImportToSceneResult,
        ImportWarning,
        ImportWarningCode,
    )

    descriptor = request.descriptor
    warnings: List[ImportWarning] = []

    # Resolve the best USD/USDZ variant
    usd_variant = _pick_usd_variant(descriptor)
    if usd_variant is None:
        return ImportToSceneResult(
            success=False,
            error_message="No USD or USDZ variant found in AssetDescriptor",
        )

    asset_path = usd_variant.local_path
    arc = request.extra.get("usd_arc", "reference")

    prim_name = re.sub(r"[^A-Za-z0-9_]", "_", descriptor.asset_id) or "Asset"
    prim_path = target_prim_path or f"/World/{prim_name}"
    prim_path = _normalize_prim_path(prim_path)

    if request.skip_existing:
        try:
            existing = list_stage(stage_file)
            existing_paths = {p["path"] for p in existing.get("prims", [])}
            if prim_path in existing_paths:
                return ImportToSceneResult(
                    success=True,
                    imported_nodes=[prim_path],
                    warnings=[
                        ImportWarning(
                            code=ImportWarningCode.UNKNOWN,
                            message=f"Prim {prim_path} already exists; skipped",
                        )
                    ],
                )
        except OpenUsdError:
            pass

    try:
        if arc == "sublayer":
            add_sublayer(stage_file, asset_path)
            imported_nodes = [prim_path]
        elif arc == "payload":
            add_payload(stage_file, prim_path, asset_path)
            imported_nodes = [prim_path]
        else:
            add_reference(stage_file, prim_path, asset_path)
            imported_nodes = [prim_path]
    except OpenUsdError as exc:
        return ImportToSceneResult(success=False, error_message=str(exc))

    # Apply placement hints
    if request.placement is not None and arc != "sublayer":
        placement = request.placement
        if detect_runtime().has_pxr and (placement.translate or placement.rotate or placement.scale):
            try:
                set_transform(
                    stage_file,
                    prim_path,
                    translate=placement.translate,
                    rotate=placement.rotate,
                    scale=placement.scale,
                )
            except OpenUsdError as exc:
                warnings.append(
                    ImportWarning(
                        code=ImportWarningCode.UNKNOWN,
                        message=f"Placement hint could not be applied: {exc}",
                    )
                )
        elif not detect_runtime().has_pxr and (placement.translate or placement.rotate or placement.scale):
            try:
                set_xform_ops(
                    stage_file,
                    prim_path,
                    translate=placement.translate,
                    rotate=placement.rotate,
                    scale=placement.scale,
                )
            except OpenUsdError as exc:
                warnings.append(
                    ImportWarning(
                        code=ImportWarningCode.UNKNOWN,
                        message=f"Placement hint could not be applied (text-fallback): {exc}",
                    )
                )

    if usd_variant.format == AssetFormat.USDZ:
        warnings.append(
            ImportWarning(
                code=ImportWarningCode.UNSUPPORTED_FEATURE,
                message="USDZ assets are referenced by path; texture unpacking is not performed",
            )
        )

    return ImportToSceneResult(
        success=True,
        imported_nodes=imported_nodes,
        warnings=warnings,
    )


# ── asset_import internal helpers ──


def _pick_usd_variant(descriptor: "AssetDescriptor") -> Optional[Any]:
    """Return the best USD or USDZ AssetFileVariant from a descriptor."""
    from dcc_mcp_core.asset_import import AssetFormat  # type: ignore

    usd_formats = {AssetFormat.USD, AssetFormat.USDZ}
    preferred = [v for v in descriptor.variants if v.preferred and v.format in usd_formats]
    if preferred:
        return preferred[0]
    fallback = [v for v in descriptor.variants if v.format in usd_formats]
    return fallback[0] if fallback else None


def _detect_composition_arcs(path: Path) -> List[str]:
    """Return a list of composition arc types present in the USD file text.

    USDZ files are zip archives (binary); text scanning is skipped for them.
    """
    arcs: List[str] = []
    if path.suffix.lower() == ".usdz":
        return arcs
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return arcs
    checks = {
        "reference": r"\breferences\s*=",
        "payload": r"\bpayload\s*=",
        "sublayer": r"\bsubLayers\s*=",
        "variant": r"\bvariantSets\s*=",
        "inherits": r"\binherits\s*=",
        "specializes": r"\bspecializes\s*=",
    }
    for arc_name, pattern in checks.items():
        if re.search(pattern, text):
            arcs.append(arc_name)
    return arcs
