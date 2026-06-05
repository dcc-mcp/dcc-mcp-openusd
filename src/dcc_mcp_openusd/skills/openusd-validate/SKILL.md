---
name: openusd-validate
description: >-
  Infrastructure skill for validating OpenUSD stage invariants and packaging a
  stage into a USDZ-style archive. Use after authoring or before handoff.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; optional usd-core for full OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: infrastructure
    search-hint: "openusd usd validate defaultPrim metersPerUnit upAxis references package usdz"
    tags: "openusd, usd, validation, usdz, package"
    tools: tools.yaml
---

# OpenUSD Validate

Validate authored stages and package them for handoff.
