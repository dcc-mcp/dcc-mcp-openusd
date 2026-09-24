---
name: openusd-material
description: >-
  Domain skill for USD material authoring. Create UsdShadeMaterial prims,
  attach PBR UsdPreviewSurface shaders, and bind materials to geometry prims.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; requires pxr (usd-core) OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd material shader PBR metallic roughness emissive clearcoat previewSurface bind UsdShade suggest unbound dangling binding fix"
    tags: "openusd, usd, material, shader, pbr, metallic, roughness, emissive, preview-surface, binding, suggest, unbound, dangling"
    tools: tools.yaml
---

# OpenUSD Material

Author materials using UsdShadeMaterial and PBR UsdPreviewSurface inputs, then bind
them to prims. Requires the pxr OpenUSD runtime — all tools fail with a
clear error when pxr is not available.

## Workflow

1. Ensure a stage exists (use `openusd-stage__create_stage` or `openusd-project`).
2. `create_material` — define a UsdShadeMaterial prim.
3. `create_preview_surface` — attach a UsdPreviewSurface shader to the material.
4. `bind_material` — bind the material onto a geometry/shading prim.

## `suggest_material_bind`

Suggests the bindings a stage is missing. It is the fix skill
`openusd_validate__validate_stage` points at for `UNBOUND_MATERIAL` and
`DANGLING_MATERIAL_BINDING`, and it reads from the same stage facts the
validator uses, so suggestions and issues never disagree.

Each suggestion is a dict with `prim_path`, `material_path`, `reason`, `detail`,
`candidates` and `auto_bindable`:

| `reason` | meaning |
| --- | --- |
| `dangling_material_binding` | `material:binding` targets a prim that does not exist |
| `non_material_binding_target` | `material:binding` targets a prim that is not a Material |
| `unbound_material` | a Material is defined but no prim binds it |
| `explicit_request` | the caller supplied both `prim_path` and `material_path` |

Candidates are ranked so the closest name comes first: a binding to
`/World/Materials/MissingPropPaint` suggests `/World/Materials/PropPaint`
before anything else. Candidates always come from prims that already exist in
the stage — there is no asset-library search. A `Scope` is never suggested as
a bind target.

Defaults to reporting: `apply` is `false`, so nothing is written. When a stage
offers no candidate at all, the tool returns success **with a `warning`** and
lists the issue under `context.unresolved` — never an empty success.

An empty suggestion list is only a healthy stage when the stage could actually
be read. A binary layer without `pxr`, a layer that failed to open, or a file
that is not a USD layer fail with `material_bind_failed` instead of reporting
"No material binding suggestions", so the tool never asserts a file it could
not inspect is clean.

```text
suggest_material_bind(stage_file)
  -> suggestions[]
     |-- dangling_material_binding    -> rebind to candidates[0]
     |-- non_material_binding_target  -> rebind to candidates[0]
     `-- unbound_material             -> bind to candidates[0]

suggest_material_bind(stage_file, prim_path, material_path, apply=true)
  -> writes the binding through bind_material and reads it back
```

`apply=true` writes through `bind_material`, which **requires the pxr runtime**.
Without pxr the call fails with `material_bind_failed` and a
`possible_solutions` entry rather than reporting a success it did not earn.
`apply=true` also requires both `prim_path` and `material_path`.
