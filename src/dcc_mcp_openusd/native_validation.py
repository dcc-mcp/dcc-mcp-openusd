"""Additional composed-stage checks which require the native USD runtime.

These checks deliberately do not load payloads or reinterpret arbitrary asset
attributes as required resources. Existing root-layer rules remain independent.
"""

from __future__ import annotations

from typing import List, Tuple

NativeIssue = Tuple[str, str, str]


def collect_native_issues(stage_file: str) -> List[NativeIssue]:
    from pxr import Usd, UsdGeom, UsdVol

    stage = Usd.Stage.Open(stage_file, load=Usd.Stage.LoadNone)
    if stage is None:
        raise RuntimeError("Could not open composed stage")
    issues: List[NativeIssue] = []
    fields = set()
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.PointInstancer):
            issues.extend(_instancer_issues(UsdGeom.PointInstancer(prim)))
        if prim.IsA(UsdVol.Volume):
            fields.update(UsdVol.Volume(prim).GetFieldPaths().values())
    for path in sorted(fields):
        field = UsdVol.OpenVDBAsset.Get(stage, path)
        if not field:
            continue
        attr = field.GetFilePathAttr()
        samples = attr.GetTimeSamples()
        times = ([Usd.TimeCode.Default()] if attr.Get() is not None or not samples else []) + samples
        for time in times:
            asset = attr.Get(time)
            # Usd resolves against the authoring layer and the stage's resolver
            # context, including package-relative paths; Path.exists cannot.
            if not asset or not asset.path or not asset.resolvedPath:
                name = asset.path if asset else "<unset>"
                issues.append(
                    (
                        "UNRESOLVED_VOLUME_ASSET",
                        f"OpenVDB field filePath '{name}' cannot be resolved at time {time}",
                        str(path),
                    )
                )
    return issues


def _instancer_issues(instancer) -> List[NativeIssue]:
    from pxr import Usd

    prim = instancer.GetPrim()
    path = str(prim.GetPath())
    required = [instancer.GetProtoIndicesAttr(), instancer.GetPositionsAttr()]
    optional_names = (
        "ids",
        "orientations",
        "orientationsf",
        "scales",
        "velocities",
        "accelerations",
        "angularVelocities",
    )
    optional = [prim.GetAttribute(name) for name in optional_names]
    optional = [attr for attr in optional if attr and attr.HasAuthoredValueOpinion()]
    samples = sorted({time for attr in required + optional for time in attr.GetTimeSamples()})
    # Static protoIndices plus time-sampled positions is legal: there is no
    # complete default snapshot to check in that case. Let USD resolve sparse
    # values at the union of samples rather than comparing authored key lists.
    times = ([Usd.TimeCode.Default()] if not samples or all(a.Get() is not None for a in required) else []) + samples
    targets = instancer.GetPrototypesRel().GetForwardedTargets()
    issues: List[NativeIssue] = []

    def add(message):
        issues.append(("INVALID_POINT_INSTANCER", message, path))

    for target in targets:
        if not prim.GetStage().GetPrimAtPath(target):
            add(f"Prototype target '{target}' does not resolve to a prim")
    for time in times:
        indices, positions = (attr.Get(time) for attr in required)
        if indices is None or positions is None:
            add(f"Required protoIndices or positions is unset at time {time}")
            continue
        count = len(indices)
        if len(positions) != count:
            add(f"positions has {len(positions)} elements but protoIndices has {count} at time {time}")
        if any(index < 0 or index >= len(targets) for index in indices):
            add(f"protoIndices contains an index outside the {len(targets)} prototypes at time {time}")
        for attr in optional:
            values = attr.Get(time)
            # Empty optional transform arrays use the native identity/default
            # behavior. IDs, when supplied, must still match instance count.
            if values is not None and (len(values) or attr.GetName() == "ids") and len(values) != count:
                add(f"{attr.GetName()} has {len(values)} elements but protoIndices has {count} at time {time}")
    return issues
