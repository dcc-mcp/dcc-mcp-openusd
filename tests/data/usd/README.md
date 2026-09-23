# USD validation samples

Sample stages used by `tests/test_validate_stage.py`. Each one triggers one of
the three high-frequency pipeline errors, and each is expected to produce the
**same** issue codes under both the `pxr` and the `text-fallback` runtime.

| file | expected error codes | what is wrong |
| --- | --- | --- |
| `broken_reference.usda` | `UNRESOLVED_REFERENCE` | `/World/SetDressing/MissingSetPiece` references `./assets/missing_set_piece.usda`, which does not exist. |
| `unit_mismatch.usda` | `UP_AXIS_MISMATCH`, `METERS_PER_UNIT_MISMATCH` | Root layer is `upAxis = "Y"` / `metersPerUnit = 1`; the sublayer `unit_mismatch_sublayer.usda` is `upAxis = "Z"` / `metersPerUnit = 0.01`. |
| `unbound_material.usda` | `DANGLING_MATERIAL_BINDING`, `INCOMPLETE_MATERIAL`, `UNBOUND_MATERIAL` | `/World/Materials/PropPaint` has no shader and is never bound; `/World/Prop` binds the non-existent `/World/Materials/MissingPropPaint`. |

`unit_mismatch_sublayer.usda` is a sublayer of `unit_mismatch.usda`, not a
standalone failure case.
