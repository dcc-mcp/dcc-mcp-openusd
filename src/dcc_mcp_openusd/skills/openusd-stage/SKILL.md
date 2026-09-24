---
name: openusd-stage
description: >-
  Domain skill for authoring and inspecting OpenUSD stages. Create a stage,
  list prims, define Xform prims, set xform operations (translate/rotate/scale),
  modify stage metadata (upAxis, metersPerUnit, framesPerSecond), and add
  reference arcs to external assets. Create portable UsdGeom.Mesh polygon
  topology and UsdGeom.Points primitives for particles and point-based FX.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.7+; optional usd-core for full OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd stage create list prim define xform reference mesh polygon points particles fx asset scene.usda broken unresolved fix repair"
    tags: "openusd, usd, stage, prims, references, mesh, polygon, points, particles, fx, fix, unresolved, repair"
    tools: tools.yaml
---

# OpenUSD Stage

Author and inspect OpenUSD stages. Prefer `openusd-project` first when creating
a new portable project folder. Use `create_points` for renderer-neutral point
effects with widths, colors, velocities, and stable ids. Use `create_mesh` for
portable polygon topology that imports consistently across DCC applications.

## `fix_reference_path`

Reports broken reference/payload asset paths and optionally rewrites them. It
is the fix skill `openusd_validate__validate_stage` points at for
`UNRESOLVED_REFERENCE`.

```text
fix_reference_path(stage_file)                       # report only
fix_reference_path(stage_file, prim_path, asset_path, apply=true)
fix_reference_path(stage_file, search_dirs=[...], apply=true)
```

Every target reports one of these statuses under `context.targets`:

| status | meaning |
| --- | --- |
| `planned` | a replacement exists and `apply` was `false` — nothing written |
| `fixed` | the reference was rewritten and the readback confirms it resolves |
| `unresolved` | no replacement was found; pass `asset_path` or `search_dirs` |
| `failed` | the fix could not be applied — see `detail` |

A replacement comes from `asset_path` when given, otherwise from a basename
search under `search_dirs` (bounded depth, so an asset library cannot turn a
fix into an unbounded scan). The search is plain filesystem walking — there is
no asset-library index.

Nothing is reported as `fixed` without a replacement that exists on disk:

- an `asset_path` that does not exist is a **failure**, never another broken
  path written into the layer;
- `asset_path` without `prim_path` is rejected when several references are
  broken, instead of guessing which one to rewrite;
- a rewrite that cannot find the authored path reports `failed` rather than
  succeeding silently.

Only the reference statements the target prim owns are rewritten, so a child
prim that happens to reference the same broken path keeps its own authoring.
Rewriting preserves comments in the layer.

A dry run that leaves a reference unresolved returns success **with a
`warning`**; the same situation under `apply=true` is an error, because the
call promised a fix. The tool is idempotent: a second run finds nothing left to
do.
