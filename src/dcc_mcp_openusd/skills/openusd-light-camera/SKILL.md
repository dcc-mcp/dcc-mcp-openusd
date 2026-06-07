---
name: openusd-light-camera
description: >-
  Domain skill for creating cameras and lights in an OpenUSD stage. Create
  UsdGeomCamera, DistantLight, SphereLight, and set transforms on prims.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; requires pxr (usd-core) OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd camera light distant sphere transform translate rotate scale"
    tags: "openusd, usd, camera, light, distant-light, sphere-light, transform"
    tools: tools.yaml
---

# OpenUSD Light & Camera

Create cameras (UsdGeomCamera) with standard lens properties, DistantLight
and SphereLight with angle/radius, intensity, and color controls. Also
provides `set_transform` for positioning any Xformable prim. Requires the pxr
OpenUSD runtime.

## Workflow

1. Ensure a stage exists.
2. Create a camera with `create_camera` and place it with `set_transform`.
3. Create lights (`create_distant_light` or `create_sphere_light`) and place them.
4. Use `set_transform` to position any Xformable prim.
