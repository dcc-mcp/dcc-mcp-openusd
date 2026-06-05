---
name: openusd-stage
description: >-
  Domain skill for authoring and inspecting OpenUSD stages. Create a stage,
  list prims, define Xform prims, and add reference arcs to external assets.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; optional usd-core for full OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd stage create list prim define xform reference asset scene.usda"
    tags: "openusd, usd, stage, prims, references"
    tools: tools.yaml
---

# OpenUSD Stage

Author and inspect OpenUSD stages. Prefer `openusd-project` first when creating
a new portable project folder.
