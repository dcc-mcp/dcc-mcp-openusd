---
name: openusd-animation
description: >-
  Domain skill for animation time samples. Set stage time codes and author
  translate/rotate/scale samples on Xformable prims as well as arbitrary
  attribute time samples.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; requires pxr (usd-core) OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd animation time samples xform keyframe timecode fps"
    tags: "openusd, usd, animation, time-samples, keyframe, xform"
    tools: tools.yaml
---

# OpenUSD Animation

Author time-sampled animation data on stages and prims. Set the stage
time range and frame rate, then write translate/rotate/scale keyframes
on Xformable prims, or generic attribute time samples. Requires the pxr
OpenUSD runtime.

## Workflow

1. Ensure a stage exists.
2. `set_time_codes` — configure start/end frame and FPS on the stage.
3. `author_xform_samples` — write translate/rotate/scale samples at specific times.
4. `author_attribute_samples` — write arbitrary attribute time samples.

## Attribute values over JSON

`author_attribute_samples` uses the existing USD attribute type. Scalar Gf
vectors (2, 3, or 4 components, including color/normal/texcoord aliases)
accept JSON arrays of the exact dimension. Components must be finite numbers;
integer vectors require integers, and booleans are rejected. Existing
array-of-vector attributes such as `points` continue to accept nested arrays.
Native Python values retain USD's existing conversion rules, including
cross-precision Gf vectors. JSON vectors are validated across the batch before
samples are authored; this is not a transaction for other USD authoring errors.
A missing custom attribute still defaults to Float. This does not add generic
relationship, API-schema, quaternion, matrix, or static-default authoring.
