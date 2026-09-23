---
name: openusd-validate
description: >-
  Infrastructure skill for validating OpenUSD stage invariants and packaging a
  stage into a USDZ-style archive. Use after authoring or before handoff.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.7+; optional usd-core for full OpenUSD runtime"
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

## `validate_stage`

Runs the same rule set whether or not the Pixar USD (`pxr`) package is
installed. `pxr` is only used to read composition facts (prim tree, references,
material bindings); every rule itself is shared, so a stage is judged
identically by the `pxr` and `text-fallback` runtimes.

Each issue is `{code, severity, message, location}`. `location` is either a
prim path (`/World/Prop`) or a `[...]` layer marker (`[unit_mismatch_sublayer.usda]`,
`[line 1]`). `severity` is `error` or `warning`; only errors make the stage
invalid. `strict: true` promotes the *missing production metadata* warnings to
errors.

| code | default severity | check |
| --- | --- | --- |
| `INVALID_STAGE_HEADER` | error | Text layer does not start with `#usda` |
| `BINARY_LAYER_REQUIRES_PXR` | error | Binary layer needs `pxr` to be validated |
| `STAGE_OPEN_FAILED` | error | Stage could not be opened |
| `MISSING_DEFAULT_PRIM` | error | No `defaultPrim` |
| `INVALID_DEFAULT_PRIM` | error | `defaultPrim` does not resolve to a prim |
| `MISSING_UP_AXIS` | warning | No `upAxis` |
| `INVALID_UP_AXIS` | error | `upAxis` is not X/Y/Z |
| `UP_AXIS_MISMATCH` | error | Sublayer `upAxis` differs from the root layer |
| `MISSING_METERS_PER_UNIT` | warning | No `metersPerUnit` |
| `INVALID_METERS_PER_UNIT` | error | `metersPerUnit` is not a positive number |
| `METERS_PER_UNIT_MISMATCH` | error | Sublayer `metersPerUnit` differs from the root layer |
| `UNRESOLVED_REFERENCE` | error | Reference/payload asset cannot be resolved on disk |
| `REFERENCE_CYCLE` | error | Reference chain loops back on itself |
| `INCOMPLETE_MATERIAL` | warning | Material has no surface output or shader |
| `DANGLING_MATERIAL_BINDING` | error | `material:binding` targets a missing or non-Material prim |
| `UNBOUND_MATERIAL` | warning | Material is defined but never bound |
| `NO_TRAVERSABLE_PRIMS` | warning | Stage has no prims |
| `UNDEFINED_PRIM_TYPE` | warning | Nested prim is defined without a type name |

The full registry is `dcc_mcp_openusd.runtime.VALIDATION_RULES`.

### Workflow

```text
validate_stage(stage_file, strict=False)
  -> valid: false, issues[].code
     |-- UNRESOLVED_REFERENCE     -> fix the asset path
     |-- UP_AXIS_MISMATCH         -> align the sublayer with the root layer
     |-- METERS_PER_UNIT_MISMATCH -> align the sublayer with the root layer
     `-- DANGLING_MATERIAL_BINDING -> rebind or author the material
```

Sample stages covering the three high-frequency errors live in
`tests/data/usd/`: `broken_reference.usda`, `unit_mismatch.usda`,
`unbound_material.usda`.
