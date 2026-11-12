# 扩展 Q/E 原生数据（2026-11-12）

已将 `Quant_LLM_Chip_Codesign` 的 `petile_full16_low32`、`petile_full16_low48` 两种配比中的全部 Q/E 格式复制到本项目。源目录保持原状；当前重放读取项目内数据，不依赖 sibling 仓库。这里的功耗数据是输入工作负载，尚不是功耗测量结果。

| 上游配比 | Q 原生 K | E 原生 K | 功能数据/每格式 | 功耗负载/每格式 |
| --- | ---: | ---: | ---: | ---: |
| `petile_full16_low32` | 96 | 192 | 961 笔 | 1024 笔 |
| `petile_full16_low48` | 128 | 256 | 961 笔 | 1024 笔 |

Q 包括 MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3，E 包括 MXFP4 E2M1、NVFP4、HiF4。Q96/Q128 已接入本轮两种 QE 扩展；不能作为 Q64 的原生 K 证据。E192/E256 是本轮新增 E-only 顶层的原生数据。

## 路径和重放

- 原始文件：`hw/power/workloads/raw/petile_extended/{functional,power}/<ratio>/<format>/<case>/`。
- 功耗来源依赖：同 raw 目录下 `provenance/manifest.json`、`provenance/sources/down_proj_samples.pt`、`provenance/sources/source_metadata.json`。
- 统一数据：`hw/power/workloads/petile_extended/normalized/{functional,power}/<format>/K<逻辑K>/<dataset>/`。
- 当前 E192/E256 的六份功能语料另发布在 `test/data/dp/{mxfp4_e2m1,nvfp4,hif4}/K{192,256}/petile_low{32,48}_native_961/`，直接参与现有 native RTL 回归与完整源指纹门禁。
- 四种 Q 的八份功能语料发布在 `test/data/dp/{mxfp8_e4m3,mxfp8_e5m2,mxfp6_e3m2,mxfp6_e2m3}/K{96,128}/petile_low{32,48}_native_961/`，用于 QE 原生 K 完整回归。
- 功耗数据集名为 `qwen3_8b_mlp_down_proj_1024`；功能数据集名为 `petile_low32_native_961` 或 `petile_low48_native_961`。

输入使用 `dp_logical_vectors_v1`，可由 `test/adapters/logical.py:read_logical_inputs` 直接读取。`expected.jsonl` 含 `exact_fp32_or_int32`、`exact_value` 及 ID/last；尚未派生 CModel 的数据中 `d=null`。CModel、冻结 RTL、门级重放和功耗门禁须继续独立完成，不能将数学参考当成已通过 RTL 的回执。

原始目录和 normalized 大型行文件不提交；[逐文件清单](raw_import_manifest.json)、[导入摘要](import_summary.json)、[导入脚本](../../scripts/import_extended_petile.py)及十四份当前回归数据进入 Git。raw 清单记录 1,011 个文件、30,792,501 字节及每份 SHA-256，包括采样依赖。上游 HEAD 为 `5a5037ad03b656ea975ef594d0aca4dc5ef96a39`；生成数据的身份以逐文件 SHA-256 为准。

首次导入到无同名产物的工作区：

```bash
python3.11 hw/power/scripts/import_extended_petile.py --source-repo /path/to/Quant_LLM_Chip_Codesign
```

脚本拒绝覆盖不同 raw 输入和已经存在的 normalized 数据；`--copy-only` 只复制并校验原始数据，`--normalize-only` 对已复制数据进行规范化。脚本读取的上游路径为 `HW/tests/data/petile_test_data/petile_ratio/`，以及 `HW/tests/data/petile_test_data/power_data/PETileRatio_Qwen8BMLPPower_1027202452/petile_ratio/`，仅选择上述两种配比中的七种 Q/E 格式。

## 映射和精度核验

完整保留源原生 K，既不裁切，也不通过重复/拼接数据扩充 K；源 C 保留且只加一次。源 16-bit word 中 E 为四个 nibble、Q 为两个 byte，低位元素在前。FP6 的源低六位移到 DP byte 的高六位。源 `group_layout` 必须是前四个 `full`、其余全部 `low`。

scale 源槽按每个四 group block 映射：Q/HiF4 复用 block 首槽，MXFP4 每两 group 共用一槽，NVFP4 每 group 独立槽。DP 打包后每个 group 都有显式 scale byte。HiF4 `sf_group0`/`sf_group1` 分别为连续的 e1/e2 位；其他格式要求这些位全零。源 metadata 的 K、类型、scale 编码、布局、事务数和数值范围均经过检查。

独立 `Fraction` 参考逐元素解量化、精确点积并加 C，最后仅作一次 FP32 RNE。共 28 数据集、27,790 笔，其中 27,784 笔与上游 FP64 golden 完全相同，另 6 笔相差 1 ULP，无非有限值不符；具体差异保存在各 manifest 的 `source_full_k_audits`。14 份真实功耗输入全部 1,024/1,024 bit-exact。六份 E 功能数据中，E192 MXFP4/NVFP4 各有一笔与源相差 1 ULP，E192 HiF4 及 E256 三格式均完全相同。

功耗窗口沿用同源 Qwen3-8B 第 0 层 MLP down_proj：1024 笔独立事务，1 GHz/II=1，取发射编号 `[256,768)` 的 512 ns 稳态窗口。其 metadata 保存原始模型 revision、采样哈希、C 的 GEMM accumulator 来源。导入没有生成 SAIF，也没有运行 Power Compiler。

已完成的实际功耗测量另见 [records 索引](../../records/README.md)。`prepare_expansion_plan.py` 在冻结模型参考目录中派生 `d`，并标记 `cmodel_status=evaluated`；原数学输入与参考不覆盖。每个计划显式绑定已通过 DC 的网表、原验证回执、模型及数据 hash。
