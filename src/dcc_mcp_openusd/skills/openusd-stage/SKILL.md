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
    search-hint: "openusd usd stage create list prim define xform reference mesh polygon points particles fx asset scene.usda"
    tags: "openusd, usd, stage, prims, references, mesh, polygon, points, particles, fx"
    tools: tools.yaml
---

# OpenUSD Stage

Author and inspect OpenUSD stages. Prefer `openusd-project` first when creating
a new portable project folder. Use `create_points` for renderer-neutral point
effects with widths, colors, velocities, and stable ids. Use `create_mesh` for
portable polygon topology that imports consistently across DCC applications.
