# Blender consumer handoff

Use this recipe when an authored USD stage will be imported into Blender.
Native stage validation and consumer verification are separate gates. The
following limits were reproduced in **Blender 4.5.14 LTS**; retest the actual
consumer version rather than treating them as permanent USD restrictions.

## PointInstancer prototypes below an untyped ancestor

A defined, untyped prim is legal USD. In the tested Blender importer, a
PointInstancer below such a container imports its point positions and Geometry
Nodes modifier, but the prototype collections are empty. Native
`ComputeInstanceTransformsAtTime` can still return every expected instance.
The same fixture with a `Scope` ancestor imports populated prototype
collections and visible instances. `support_scene_instancing=False` does not
avoid this PointInstancer-specific case.

For a newly authored Blender-targeted hierarchy, define organizational parents
as `Scope`, or use `Xform` when transformation semantics are intended, before
authoring the instancer. Prefer the available typed tools, such as
`openusd_stage__define_xform`, where appropriate. Inspect existing prim types
and composition first: do not recursively retag arbitrary source layers or
replace existing schemas. An opt-in, narrowly scoped stronger layer can record
an approved consumer workaround without rewriting a shared source asset.

After import, verify all of these, not merely a POINTCLOUD object count:

- point count and prototype index, position, orientation and scale arrays;
- each Geometry Nodes Collection Info input and its populated prototype
  collections, including actual mesh geometry;
- evaluated instance count and representative world transforms;
- a small local render showing the intended geometry and scale.

## Missing float3 primvar fallback

`UsdPrimvarReader_float3` has a defined `inputs:fallback` for a missing primvar.
The tested importer creates a Blender Attribute node but does not preserve
that fallback. A missing `displayColor` can therefore produce a black surface
despite a nonblack USD fallback. A mesh with the corresponding authored
primvar, and a constant Preview Surface material, are useful positive controls.

Where the intended value is known, explicitly author `primvars:displayColor`
on only the affected geometry, with the correct array type, interpolation and
length. Do not overwrite existing vertex/face-varying colors, silently flatten
time samples, or apply one global color to objects with different materials.
For a genuinely constant material, author a constant Preview Surface input
instead of an unnecessary primvar connection. Neither workaround changes the
validity of native USD fallback behavior.

Read back the imported attribute and material node connection. Compare a
small lit render against the constant-color control before a full render.
Record any consumer-only material repair explicitly.

## Reproduction and evidence scope

`tests/fixtures/blender_consumer/` contains two self-contained, procedural
USDA fixtures with no external textures or production assets:

- `pointinstancer.usda`: two asymmetric mesh prototypes and three transformed
  instances per group; the left group has an untyped parent, the right a Scope.
- `material_fallback.usda`: three planes using a constant color, an authored
  `displayColor`, and a missing primvar with the same fallback, respectively.

The native fixture tests verify valid authored data; they do **not** prove a
Blender importer fix. Importing and rendering the fixtures exercises the
consumer boundary. Keep the original failing case when testing a workaround.

Source references:

- [OpenUSD Preview Surface and primvar readers](https://openusd.org/release/spec_usdpreviewsurface.html)
- [Blender 4.5.14 prototype collection traversal](https://github.com/blender/blender/blob/v4.5.14/source/blender/io/usd/intern/usd_reader_stage.cc)
- [Blender 4.5.14 material conversion](https://github.com/blender/blender/blob/v4.5.14/source/blender/io/usd/intern/usd_reader_material.cc)

These checks establish consumer compatibility, not photorealistic art quality.
