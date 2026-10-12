# Native validation and packaging boundaries

## English

The original metadata/composition/material rules still inspect root-layer facts
in both runtimes. With Pixar USD installed, `validate_stage` also checks the
current composed stage using `Usd.Stage.LoadNone`:

- `UNRESOLVED_VOLUME_ASSET`: a `Volume`-connected `OpenVDBAsset.filePath` is empty
  or unresolved, at its default or authored time samples. USD resolves against
  the authoring layer and resolver context, including assets within packages.
  An unconnected field or arbitrary optional asset attribute is not an error.
- `INVALID_POINT_INSTANCER`: `positions`/`protoIndices` cardinality differs;
  an authored nonempty optional per-instance array has the wrong cardinality;
  authored `ids` differs in length; a prototype index is out of range; or a
  prototype target does not exist. Sparse samples are evaluated at their union.
  Optional arrays may be omitted, empty transform arrays use native defaults,
  and `invisibleIds` is a sparse ID mask, not a per-instance array. A valid
  prototype prim with an unloaded payload is not a missing target.

Payload contents are not loaded by these new rules. Inactive prims and
unselected variants are outside these composed semantic checks. Existing
root-layer reference rules are unchanged. These are bounded checks, not a full
USD compliance checker, VDB decoder, or physics solver.

`native_checks` reports `performed`, `unavailable`, or `failed`. Text-fallback
cannot check these composed semantics and explicitly reports `unavailable`.

`package_usdz` uses `UsdUtils.ComputeAllDependencies` before native packaging.
Unresolved dependencies fail before an existing output is touched. A failed
native packager no longer silently produces a root-only ZIP. Successful native
packaging is staged in a temporary sibling directory and atomically replaces
the destination; `complete: true` describes dependency completeness, not visual
correctness or host support. Source and output must differ.

Optional external assets can be legal in ordinary USD, but a self-contained
USDZ must include its dependencies. Packaging is intentionally stricter than
stage validation. Repair/remove unused missing paths, or keep the scene as
ordinary USD when external resources are intentional. No dependency is
silently stripped. Without pxr, the existing root-only ZIP mode reports
`dependency_check: "unavailable"`, `complete: null`, and `unresolved_assets: []`
(the empty list means no check was performed, not that everything resolved).
Native success reports `dependency_check: "performed"`, `complete: true`, and
`unresolved_assets: []`.

A complete package does not imply universal host consumption: the separate
Blender 4.5.14 probe decoded an external VDB but not the same grid inside USDZ.
That host limitation is not reported as a USD schema error.

## 中文

原有根层元数据、引用和材质规则继续适用于两种运行模式。安装原生 pxr 后，
验证额外检查当前组合场景中的两类语义，并且不会主动加载 payload：

- `UNRESOLVED_VOLUME_ASSET`：被 Volume 字段关系使用的 OpenVDBAsset 文件为空
  或无法解析。检查默认值和已写入的时采样，使用 USD 自身的层相对路径与解析器。
  未连接的可选字段、普通可选 asset 属性不会被当成必需体积依赖。
- `INVALID_POINT_INSTANCER`：实例位置、原型索引、ID 或已提供的非空变换数组
  长度不一致，原型索引越界，或目标 prim 不存在。支持稀疏采样、缺省/空变换数组
  和稀疏 invisibleIds。目标 prim 存在但其 payload 未加载，不等于目标缺失。

新增检查不覆盖未激活 prim、未选择 variant 或未加载 payload 的内容，也不是
完整 USD 合规验证、VDB 内容解码或动力学求解。`native_checks` 明确返回执行、
不可用或失败；文本回退不冒称完成原生检查。

原生 USDZ 打包先检查全部文件依赖。缺失资源会返回错误且保留原输出；原生打包
失败不再悄悄降级成只含根层的 ZIP。成功后才替换目标。普通 USD 可以保留合法的
可选外部资源，但完整自包含 USDZ 的依赖要求更严格，不会静默删除缺失路径。
文本回退仍可生成根层 ZIP，不过会明确返回 `complete: null`，不宣称依赖完整。

包内依赖完整不代表每个宿主都能消费。例如独立的 Blender 4.5.14 实测能解码
外置 VDB，却不能读取 USDZ 内的同一体积；这是宿主边界，不是本验证器的 schema 错误。

## References

- [PointInstancer schema and sampling](https://openusd.org/release/api/class_usd_geom_point_instancer.html)
- [OpenVDBAsset schema](https://openusd.org/release/api/class_usd_vol_open_v_d_b_asset.html)
- [Dependency discovery](https://openusd.org/release/api/dependencies_8h.html)
- [Native USDZ packaging](https://openusd.org/release/api/usdz_package_8h.html)
