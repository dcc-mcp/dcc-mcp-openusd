# USD validation samples

Sample stages used by `tests/test_validate_stage.py`. Every stage is expected
to produce the **same** `code` / `severity` / `location` under both the `pxr`
and the `text-fallback` runtime; `test_pxr_and_fallback_report_the_same_codes_on_every_fixture`
asserts that over all of them.

## High-frequency errors

| file | expected codes | what is wrong |
| --- | --- | --- |
| `broken_reference.usda` | `UNRESOLVED_REFERENCE` | `/World/SetDressing/MissingSetPiece` references `./assets/missing_set_piece.usda`, which does not exist. |
| `unit_mismatch.usda` | `UP_AXIS_MISMATCH`, `METERS_PER_UNIT_MISMATCH` | Root layer is `upAxis = "Y"` / `metersPerUnit = 1`; the sublayer `unit_mismatch_sublayer.usda` is `upAxis = "Z"` / `metersPerUnit = 0.01`. |
| `unbound_material.usda` | `DANGLING_MATERIAL_BINDING`, `INCOMPLETE_MATERIAL`, `UNBOUND_MATERIAL` | `/World/Materials/PropPaint` has no shader and is never bound; `/World/Prop` binds the non-existent `/World/Materials/MissingPropPaint`. |

## Collector-equivalence regressions

These look like healthy stages but trip specific parser/collector defects, so
the parity test covers the branches the three samples above miss.

| file | expected codes | what it pins |
| --- | --- | --- |
| `custom_data_prim.usda` | `UNRESOLVED_REFERENCE` @ `/World/Body` | The prim header carries `customData = { ... }`; the body brace must be found after the balanced header parens, otherwise the body leaks into the parent and the reference is reported against `/World`. |
| `sublayer_offset.usda` | `UP_AXIS_MISMATCH`, `METERS_PER_UNIT_MISMATCH`; **no** `MISSING_UP_AXIS` | `subLayers = [@./sublayer_offset_sub.usda@ (offset = 10; scale = 1)]` puts a `)` inside the metadata block, which must be matched by paren depth rather than the first `)`. |
| `nested_reference.usda` | none (`valid: true`) | `nested/inner.usda` references `./prop.usda` relative to its own directory; reference assets are resolved against the root layer directory, so this must not be a false `UNRESOLVED_REFERENCE`. |
| `purpose_binding.usda` | none (`valid: true`) | `material:binding:preview` counts as a binding in both runtimes (no false `UNBOUND_MATERIAL`), while `material:binding:collection:proxy` targets a collection and is ignored by both (no false `DANGLING_MATERIAL_BINDING`). |

## Supporting layers

These are composed layers, not standalone failure cases:

- `unit_mismatch_sublayer.usda` — sublayer of `unit_mismatch.usda`
- `sublayer_offset_sub.usda` — sublayer of `sublayer_offset.usda`
- `nested/inner.usda`, `nested/prop.usda` — reference chain of `nested_reference.usda`
