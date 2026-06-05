---
name: openusd-project
description: >-
  Domain skill for creating and maintaining self-contained OpenUSD project
  folders with scene.usda, assets, materials, lights, packages, and snapshots.
  Use before authoring a new OpenUSD stage or when resuming a portable project.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; optional usd-core for full OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd project folder create resume snapshot assets scene.usda package portable"
    tags: "openusd, usd, project, stage, asset-pipeline"
    tools: tools.yaml
---

# OpenUSD Project

Create self-contained OpenUSD project folders and stage snapshots.

## Workflow

1. Use `openusd_project__create_project` to create the folder layout and root
   `scene.usda`.
2. Load `openusd-stage` to author prims and references.
3. Load `openusd-validate` to validate or package the stage.
