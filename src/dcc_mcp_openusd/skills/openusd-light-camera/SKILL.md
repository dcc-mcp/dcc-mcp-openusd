---
name: openusd-light-camera
description: >-
  Domain skill for creating cameras and lights in an OpenUSD stage. Create
  UsdGeomCamera, DistantLight, SphereLight, HDR DomeLight, and set transforms or visibility on prims.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; requires pxr (usd-core) OpenUSD runtime"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd camera light distant sphere dome HDRI transform visibility hide show"
    tags: "openusd, usd, camera, light, distant-light, sphere-light, dome-light, hdri, transform, visibility"
    tools: tools.yaml
---

# OpenUSD Light & Camera

Create cameras (UsdGeomCamera) with standard lens properties, DistantLight
SphereLight with angle/radius, intensity, and color controls, plus DomeLight
with HDR environment texture and exposure controls. Also
provides `set_transform` for positioning any Xformable prim and `set_visibility`
for beauty/FX layer control on Imageable prims. Requires the pxr
OpenUSD runtime.

## Workflow

1. Ensure a stage exists.
2. Create a camera with `create_camera` and place it with `set_transform`.
3. Create lights (`create_distant_light`, `create_sphere_light`, or `create_dome_light`) and place them.
4. Use `set_transform` to position any Xformable prim.
5. Use `set_visibility` to include or exclude Imageable prims from a render layer.
