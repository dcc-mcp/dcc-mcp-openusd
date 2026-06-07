---
name: openusd-material
description: >-
  Domain skill for USD material authoring. Create UsdShadeMaterial prims,
  attach UsdPreviewSurface shaders, and bind materials to geometry prims.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; requires pxr (usd-core) OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd material shader previewSurface bind UsdShade"
    tags: "openusd, usd, material, shader, preview-surface, binding"
    tools: tools.yaml
---

# OpenUSD Material

Author materials using UsdShadeMaterial and UsdPreviewSurface, then bind
them to prims. Requires the pxr OpenUSD runtime — all tools fail with a
clear error when pxr is not available.

## Workflow

1. Ensure a stage exists (use `openusd-stage__create_stage` or `openusd-project`).
2. `create_material` — define a UsdShadeMaterial prim.
3. `create_preview_surface` — attach a UsdPreviewSurface shader to the material.
4. `bind_material` — bind the material onto a geometry/shading prim.
