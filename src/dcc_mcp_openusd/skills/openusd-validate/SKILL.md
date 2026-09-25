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
installed. `pxr` is only used to parse the file (`Sdf.Layer`); every rule is
shared, so a stage is judged identically by the `pxr` and `text-fallback`
runtimes.

Both runtimes report facts for the **root layer only** — prims composed in
from references and sublayers are out of scope. That keeps the two collectors
equivalent and means reference asset paths always resolve against the root
layer's directory. Layer-level metadata (`upAxis`, `metersPerUnit`) is still
compared across the whole `subLayers` chain.

Prims authored inside a `variantSet` block **are** reported, at the flat path
they compose to (`/Root/Looks/RedMat`), and every variant is reported rather
than only the selected one. That way a binding pointing into a variant never
looks dangling. A Material counts as complete when it has an `outputs:surface`
authoring or a Shader at any depth beneath it.

### Issue shape

Each issue is the frozen `ValidationIssue` schema:
`{code, severity, message, location, strict_promoted, suggested_fix, next_steps}`.

`severity` is `error`, `warning` or `info`; only errors make the stage invalid.
`strict: true` promotes the *missing production metadata* warnings to errors and
sets `strict_promoted: true` on exactly those issues, so you can tell an issue
that is an error on its own from one that only became an error because the run
was strict.

`location` is a **discriminated object**, not an overloaded string. Read `kind`
to know which address space you are in, then read the one member that kind uses
— the other is always `null`:

| `kind` | `path` | `line` | example `label` |
| --- | --- | --- | --- |
| `prim` | SdfPath | `null` | `/World/Prop` |
| `layer` | layer / file | `null` | `[unit_mismatch_sublayer.usda]` |
| `line` | `null` | line number | `[line 1]` |

`label` is display-only: it keeps the old string form so existing logs and UI
still render. **Do not parse it** — parse `kind`, `path` and `line`.

```json
{
  "code": "UNRESOLVED_REFERENCE",
  "severity": "error",
  "message": "Reference './assets/prop.usda' cannot be resolved on disk",
  "location": {"kind": "prim", "path": "/World/Prop", "line": null, "label": "/World/Prop"},
  "strict_promoted": false,
  "suggested_fix": {"skill": "openusd_stage__fix_reference_path", "args": {"stage_file": "/work/scene.usda"}},
  "next_steps": [{"action": "openusd_stage__fix_reference_path", "args": {"stage_file": "/work/scene.usda"}}]
}
```

### Result shape

The payload is a `ValidationResult`: `{success, message, stage_file, issues,
summary, next_steps}`.

- `summary` counts every severity and adds `total`, so `summary.error == 0` is
the same claim as `success`. All four keys are always present.
- `message` is that summary in words, e.g. `3 issues (1 error, 2 warnings)`.
- `next_steps` aggregates every issue's steps (duplicates collapsed) so you can
act without walking `issues`.
- `valid` and `issue_count` are deprecated aliases of `success` and
`summary.total`, kept for one migration window.

### `suggested_fix` and `next_steps`

`suggested_fix` is the machine-readable fix for the issue, or `null` when no
fix skill covers the rule. Its shape is `{"skill": "<family>__<tool>", "args": {...}}`:

```json
{
  "skill": "openusd_stage__fix_reference_path",
  "args": {"stage_file": "/work/scene.usda", "prim_path": "/World/Prop"}
}
```

`next_steps` is a list that is never empty, so an agent always has a next move.
For a rule with a fix skill the single entry is that skill plus its `args`; for
every other rule it is `{action: "manual_fix", detail: "..."}` with the same
advice a human would give.

| code | `suggested_fix.skill` |
| --- | --- |
| `UNRESOLVED_REFERENCE` | `openusd_stage__fix_reference_path` |
| `DANGLING_MATERIAL_BINDING` | `openusd_material__suggest_material_bind` |
| `UNBOUND_MATERIAL` | `openusd_material__suggest_material_bind` |

Both fix skills work without pxr for reporting and read back what they write,
so the loop `validate -> suggested_fix -> validate` is safe to automate.

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
     |-- UNRESOLVED_REFERENCE      -> openusd_stage__fix_reference_path
     |-- DANGLING_MATERIAL_BINDING -> openusd_material__suggest_material_bind
     |-- UNBOUND_MATERIAL          -> openusd_material__suggest_material_bind
     |-- UP_AXIS_MISMATCH          -> align the sublayer with the root layer
     `-- METERS_PER_UNIT_MISMATCH  -> align the sublayer with the root layer
```

Sample stages covering the three high-frequency errors live in
`tests/data/usd/`: `broken_reference.usda`, `unit_mismatch.usda`,
`unbound_material.usda`.
