# dcc-mcp-openusd Skills

Bundled OpenUSD skills are intentionally small and progressive:

- `openusd-project`: project folder lifecycle and snapshots.
- `openusd-stage`: stage authoring and inspection.
- `openusd-validate`: validation and USDZ-style packaging.
- `openusd-material`: material authoring (UsdShadeMaterial, UsdPreviewSurface) and binding.
- `openusd-light-camera`: camera (UsdGeomCamera) and light (DistantLight, SphereLight) creation with transforms.
- `openusd-animation`: stage time codes and translate/rotate/scale time samples.
- `openusd-composition`: sublayers, payloads, variant sets, and variant selections for multi-layer scenes.

Load only the skill needed for the current task, then follow the declared
`next-tools` hints.
