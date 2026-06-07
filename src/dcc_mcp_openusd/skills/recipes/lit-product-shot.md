# lit-product-shot Recipe

Create a product showcase scene with materials, lighting, and camera.

## Workflow

1. Create a stage (or project) with `openusd-stage__create_stage`.
2. Place geometry — use `openusd-stage__define_xform` for the product base and optional
   environment prims (floor/wall/backdrop).
3. If external assets are available, use `openusd-stage__add_reference` to compose them.
4. Author materials:
   - `openusd-material__create_material` for each shading prim.
   - `openusd-material__create_preview_surface` with a plausible `diffuse_color`.
   - `openusd-material__bind_material` to attach each material.
5. Place a camera:
   - `openusd-light-camera__create_camera` with focal_length=35, f_stop=4.
   - `openusd-light-camera__set_transform` to position the camera.
6. Add lighting:
   - `openusd-light-camera__create_distant_light` as a key light (angle=0.53, intensity=2, color=[1,1,1]),
     then `set_transform` to rotate it.
   - `openusd-light-camera__create_sphere_light` as a rim light (radius=0.1, intensity=5, color=[0.8,0.9,1]),
     then `set_transform` to position it behind the product.
7. Validate with `openusd-validate__validate_stage`.

## Expected prims

- `/World`
- `/World/ProductBase`, `/World/Floor`, `/World/Backdrop` (Xform)
- `/World/Mat_Product`, `/World/Mat_Floor` (Material)
- `/World/Camera` (Camera)
- `/World/KeyLight` (DistantLight), `/World/RimLight` (SphereLight)

## Notes

- Use the pxr-required tools — failing early without OpenUSD is expected.
- Default colors: matte white for backdrop, dark grey for floor, plausible product color.
