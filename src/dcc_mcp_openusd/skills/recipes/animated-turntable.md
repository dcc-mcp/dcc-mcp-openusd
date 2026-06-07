# animated-turntable Recipe

Create a turntable animation where an object rotates 360 degrees.

## Workflow

1. Create a stage (or project) with `openusd-stage__create_stage`.
2. Place geometry:
   - If using an external asset, add it via `openusd-stage__add_reference` at `/World/Asset`.
   - Otherwise, create a simple placeholder Xform at `/World/Asset`.
3. Place a camera:
   - `openusd-light-camera__create_camera` at `/World/Camera`.
   - Position it with `openusd-light-camera__set_transform` — translate back and up
     (e.g. [0, 2, 15]), then rotate to look down at the asset.
4. Add simple lighting:
   - `openusd-light-camera__create_distant_light` as fill.
   - `openusd-light-camera__create_sphere_light` as accent.
5. Set animation range:
   - `openusd-animation__set_time_codes` with start=1, end=120, fps=24.
6. Author rotation animation on the asset:
   - `openusd-animation__author_xform_samples` on `/World/Asset` with samples
     that rotate the Y axis from 0 to 360 over the time range.
     Sample format: `[{"time": 1, "rotate": [0, 0, 0]}, ..., {"time": 120, "rotate": [0, 360, 0]}]`.
7. Validate with `openusd-validate__validate_stage`.

## Expected prims

- `/World`
- `/World/Asset` (Xform, animated rotate Y 0→360)
- `/World/Camera` (Camera)
- `/World/FillLight` (DistantLight), `/World/AccentLight` (SphereLight)

## Sample keyframes (24 fps, 120 frames)

| Frame | rotate Y  |
|-------|-----------|
| 1     | 0         |
| 30    | 90        |
| 60    | 180       |
| 90    | 270       |
| 120   | 360       |
