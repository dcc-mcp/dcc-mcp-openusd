# layered-set-dressing Recipe

Build a multi-layered scene using composition arcs: sublayers, references, and variants.

## Workflow

1. Create the root stage with `openusd-stage__create_stage`.
2. Prepare auxiliary layer files:
   - Create `props.usda` (a separate stage) with furniture/props geometry.
   - Create `lighting.usda` (a separate stage) with lights already placed.
3. Compose layers onto the root stage:
   - `openusd-composition__add_sublayer` to add `props.usda` to the root layer.
   - `openusd-composition__add_sublayer` to add `lighting.usda` to the root layer.
4. Reference external hero assets:
   - `openusd-stage__add_reference` at `/World/Hero` pointing to a hero asset file.
5. Add variants on a prim (e.g. `/World/Hero`):
   - `openusd-composition__add_variant_set` with name "lod".
   - Each variant should be authored in separate variant blocks within the
     referenced asset or in sub-layers. The `set_variant_selection` tool
     switches between them.
6. Add payloads for deferred loading:
   - `openusd-composition__add_payload` on `/World/ComplexDress` pointing to
     a high-resolution asset that should load on demand.
7. Validate with `openusd-validate__validate_stage`.

## Expected prims

- `/World` (stage root)
- `/World/Hero` (Xform, with reference arc + "lod" variant set)
- `/World/ComplexDress` (Xform, with payload arc)
- Props from `props.usda` (via sublayer)
- Lights from `lighting.usda` (via sublayer)

## Composition arc summary

| Arc type     | Prim            | Purpose               |
|-------------|-----------------|------------------------|
| sublayer    | root layer      | props, lighting        |
| reference   | /World/Hero     | hero asset             |
| variant set | /World/Hero     | LOD switching          |
| payload     | /World/ComplexDress | deferred heavy asset |
