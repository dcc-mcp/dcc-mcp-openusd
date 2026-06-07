---
name: openusd-composition
description: >-
  Domain skill for OpenUSD composition arcs. Add sublayers, payloads, variant
  sets, and variant selections to build multi-layer scenes.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; requires pxr (usd-core) OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd composition sublayer payload variant set selection reference layer"
    tags: "openusd, usd, composition, sublayer, payload, variant, variant-set"
    tools: tools.yaml
---

# OpenUSD Composition

Manage layer composition arcs: add sublayers to the root layer, attach
payload arcs on prims, create variant sets, and set variant selections.
Reference arcs remain in `openusd-stage`. Requires the pxr OpenUSD runtime.

## Workflow

1. Ensure a stage exists.
2. `add_sublayer` — compose another layer under the root layer.
3. `add_payload` — attach a payload arc on a prim.
4. `add_variant_set` — create a named variant set on a prim.
5. `set_variant_selection` — switch the active variant in a variant set.
