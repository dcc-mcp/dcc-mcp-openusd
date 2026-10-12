# Portable UV textures / 可移植 UV 纹理

These two typed tools author native USD shading data. They require `usd-core`
(`pxr`), write the selected stage's **root layer**, and save the result. They do
not bake images, render, or turn renderer-specific nodes into portable USD.

这两个 typed 工具编写原生 USD 着色数据，需要 `usd-core`（`pxr`），将修改写入
指定舞台的**根层**并保存。它们不会烘焙图片、执行渲染或转换渲染器专用节点。

## English

### 1. Author mesh UVs

Load `openusd-stage`, discover `set_mesh_uvs`, and describe the returned slug.
Use that actual slug with `dcc-mcp-cli call`:

```json
{
  "stage_file": "/project/scene.usda",
  "prim_path": "/World/Panel",
  "uvs": [[0, 0], [1, 0], [1, 1], [0, 1]],
  "interpolation": "faceVarying",
  "indices": [0, 1, 2, 3],
  "primvar_name": "st"
}
```

The mesh must already exist with default-time topology. This authors
`primvars:st` with the `texCoord2f[]` role. `faceVarying` needs one element per
face corner; `vertex` needs one per point. With indices, the index count must
match that size and each index must address the supplied UV array. Without
indices, the UV count must match that size. Values must be finite float32s.

Omitting `indices` blocks old indices, including indices inherited from a
sublayer; it does not leave a stale indexing array behind. Repeated calls
replace the named static UV primvar. Existing animated UVs or incompatible
attribute types are rejected. Other UV sets and source asset layers are left
alone. The `primvar_name` omits the `primvars:` prefix and must match the
texture reader's `texcoord_name`. UVs use USD's lower-left image origin.

### 2. Connect a Preview Surface texture

Create a material and its Preview Surface with the existing material tools.
Load `openusd-material`, discover `connect_preview_surface_texture`, describe
its slug, then call it:

```json
{
  "stage_file": "/project/scene.usda",
  "material_path": "/World/Materials/Stone",
  "texture_file": "textures/stone_basecolor.png",
  "input_name": "diffuseColor",
  "texcoord_name": "st"
}
```

`texture_file` must be an existing local file. Relative inputs resolve against
the **stage file's directory**, regardless of the CLI working directory. The
authored `asset` value is relative to that layer when the filesystem allows
it. Move the containing project together or package it with the native
`package_usdz` tool to keep dependencies. An arbitrary filename's existence
is checked; image decoding and renderer support are the consumer's concern.
UDIM patterns, remote resolvers, and texture copying are outside this tool.

The network is `UsdPrimvarReader_float2 → UsdUVTexture → UsdPreviewSurface`.
The reader uses a string `varname`, a float2 output, and a matching mesh UV set.

- `diffuseColor`, `emissiveColor`: `rgb`, default `sRGB` source color space.
- `roughness`, `metallic`, `opacity`, `clearcoat`, `clearcoatRoughness`,
  `occlusion`: choose `r`, `g`, `b`, or `a`; default `r` and `raw`.
- `normal`: `rgb` and `raw` only; unsigned tangent-space maps in [0, 1] are
  decoded with scale `(2, 2, 2, 1)` and bias `(-1, -1, -1, 0)`. Signed/HDR
  normal maps require a different network and are outside this helper.

Explicit `source_color_space` accepts `sRGB`, `raw`, or `auto` (normal requires
`raw`). `wrap_s` and `wrap_t` accept `repeat` (default), `clamp`, `mirror`,
`black`, or `useMetadata`. No automatic UV generation occurs.

The default shader is the material's resolved universal surface shader.
`shader_path` may select another existing Preview Surface inside the same
material. The material's surface output is not rewired. Other shader input
values/connections are preserved. Two deterministic sibling paths per input,
`<shader>_<input>Texture` and `<shader>_<input>Primvar`, are reused on repeat
calls. Reserve these paths for this helper; incompatible existing nodes,
properties, or animated configuration inputs are rejected before saving.

This is a portable Preview Surface subset. Different renderers can interpret
translucency, normal mapping, and color management differently. Native
save/reopen and dependency packaging verify data correctness; they do not
certify identical images across renderers. Variant-body authoring,
instanceable metadata authoring, and arbitrary shader graphs remain separate
capability gaps.

## 中文

### 1. 编写网格 UV

加载 `openusd-stage`，搜索并 describe `set_mesh_uvs`，随后用实际返回的 slug
调用。上方第一个 JSON 为单四边形示例。网格必须已存在且具有默认时间的拓扑。
工具生成 `texCoord2f[]` 类型的 `primvars:st`：

- `faceVarying`：每个面角一个元素，支持接缝
- `vertex`：每个网格点一个元素
- 提供 `indices` 时，索引数量必须与元素数量相符，且索引不得越界
- 不提供索引时，UV 数量必须与元素数量相符，并阻断旧的或弱层继承的索引

坐标必须是有限 float32 值；重复调用会替换指定的静态 UV。已有动画 UV 或类型
不兼容的属性会被拒绝。其他 UV 集和源资产层不变。`primvar_name` 不带
`primvars:` 前缀，并应与材质的 `texcoord_name` 相同。USD 的纹理原点位于左下角。

### 2. 连接 Preview Surface 纹理

先用现有工具创建材质及 Preview Surface，再加载 `openusd-material`，发现并
调用 `connect_preview_surface_texture`。上方第二个 JSON 为颜色贴图示例。
`texture_file` 必须存在；相对路径以**舞台文件所在目录**为基准，不以 CLI 当前
目录为基准。工具将资源路径保存为相对路径（文件系统允许时），方便整体搬迁项目
或通过原生 `package_usdz` 打包。只检查文件存在，不验证图片解码或渲染器兼容性；
目前不支持 UDIM 模式、远程资源解析或自动复制图片。

工具创建标准的 Primvar Reader → UV Texture → Preview Surface 连接：

- 颜色和自发光使用 `rgb`，默认 `sRGB`
- 粗糙度、金属度、透明度、清漆及遮蔽使用单通道，默认 `r` + `raw`
- 法线使用 `rgb` + `raw`，将 [0, 1] 的无符号切线空间贴图通过 scale=2、bias=-1
  解码；已带符号/HDR 法线不属于此快捷工具的范围

支持指定采样通道、颜色空间、UV 集和两个方向的环绕模式。不会自动展开 UV。
默认编辑材质已连接的通用表面 shader；也可通过 `shader_path` 指定材质内的
另一个现有 Preview Surface，但不会改变材质表面输出。每个输入有独立、可重复
使用的两个节点，其他输入与源资产层保持不变。只保存根层的修改。

这是可移植 Preview Surface 的有限接口，不能保证所有渲染器图像完全一致。
原生保存重开、相对路径搬迁及 USDZ 打包测试证明的是数据正确性。Variant 内容
编写、instanceable 元数据及任意着色图接口仍需独立支持。

## Official references / 官方依据

- [UsdPreviewSurface and texture/primvar nodes](https://openusd.org/release/spec_usdpreviewsurface.html)
- [UsdGeomPrimvar indexing and interpolation](https://openusd.org/release/api/class_usd_geom_primvar.html)
- [Simple shading tutorial](https://openusd.org/release/tut_simple_shading.html)
