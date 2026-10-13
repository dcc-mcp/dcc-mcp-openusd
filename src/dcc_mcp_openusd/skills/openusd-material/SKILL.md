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
    search-hint: "openusd usd material shader PBR metallic roughness emissive clearcoat previewSurface texture UV normal map sRGB raw bind UsdShade suggest unbound dangling binding fix"
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

## `connect_preview_surface_texture`

Connect an existing local texture to an existing Preview Surface through
`UsdUVTexture` and `UsdPrimvarReader_float2`. Relative `texture_file` inputs
resolve against the stage directory; the root layer stores a relative asset
path where possible. No files are copied or baked. Create matching mesh UVs
with `openusd_stage__set_mesh_uvs` first.

Color inputs default to `rgb`/`sRGB`; scalar data defaults to `r`/`raw` and
accepts `r`, `g`, `b`, or `a`. `normal` requires `rgb`/`raw` and assumes an
unsigned [0,1] tangent-space map, applying scale 2 and bias -1. Signed normal
maps, UDIM patterns, and arbitrary shader graphs are outside this helper.

Repeated calls reuse two reserved sibling paths for each shader/input,
`<shader>_<input>Texture` and `<shader>_<input>Primvar`. Other input connections
and source layers remain unchanged. Incompatible nodes/properties or animated
configuration inputs fail before saving. `shader_path` optionally chooses an
existing Preview Surface inside the material; the surface output is not
rewired. Move the project with its textures or use native USDZ packaging.

中文：连接标准颜色、粗糙度、金属度、透明度、清漆、遮蔽及法线纹理。相对路径以
舞台目录为基准；需要匹配的网格 UV。重复调用更新当前根层中的专用节点，不会修改
源资产层。原生数据可移植不代表不同渲染器的画面完全一致。

## Blender consumer handoff

For PointInstancer prototypes or primvar-driven materials consumed by Blender,
read [the Blender handoff recipe](../recipes/blender-consumer-handoff.md).
It records version-specific importer limits and opt-in authoring workarounds;
these are not native USD validity rules.
