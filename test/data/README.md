# DP 共用测试数据

功能：保存现用 CModel/Verilog 共用的 packed 端口数据，以及新混合 DP 的逻辑向量。更新于2026-11-07；现用适配器见 [cmodel.py](../adapters/cmodel.py)，新逻辑数据适配器见 [logical.py](../adapters/logical.py)。

目录 `dp/<format>/K<logical_k>/<dataset>/` 的 K 是该格式的实际元素数。现用 `DP_INPUTS_V1` manifest 中 k_fp16 是硬件基准 K，两者不能混用；现用数据全部 k_fp16=16，因此 T8/H16/Q32/E64/INT32项。新增逻辑 schema 没有 k_fp16 字段。

## inputs.txt

```text
DP_INPUTS_V1
<请求数> <k_fp16>
<id> <a_datatype> <b_datatype> <c_datatype> <a_scale_datatype> <b_scale_datatype> <last> <a> <b> <c> <a_scale> <b_scale> <a_e1> <a_e2> <b_e1> <b_e2>
```

每条固定16个空格分隔字段：前7个十进制（last=0/1），后9个无 `0x` 的定宽十六进制。高位写左侧，逻辑低索引元素在总线低位。TF32 低13位补零；FP6 编码放每byte高6位、低2位零；4位格式紧密排列。

| 文件字段 | DP 信号 | 位数 |
| --- | --- | --- |
| a / b | in_a / in_b | 16×k_fp16，各侧 |
| c | in_c | 32 |
| a_scale / b_scale | in_scale_a / in_scale_b | 8×G |
| a_e1 / b_e1 | in_hif4_e1_a / b | 4×G |
| a_e2 / b_e2 | in_hif4_e2_a / b | 2×G |
| a_scale_datatype / b_scale_datatype | in_scale_a_datatype / b | 2 |
| a_datatype / b_datatype / c_datatype | 同名 in_ 前缀 | 4 / 4 / 1 |
| last | in_last | 1 |
| id | 无 DUT 信号，scoreboard 软件编号 | 非负整数 |

G=k_fp16/4；十六进制字符数为 ceil(bits/4)，未使用的最高位必须零。datatype 编码：[DP interface](../../src/spec/dp/dptop/interface.md)。scale 按基本组展开：MXQ四槽相同；MXFP4槽0=1、2=3；HiF4四槽相同；NV四槽独立。HiF e1每4元素、e2每8元素按低索引bit排列。无scale/meta的格式写全零。

这份文件已经是物理端口 layout；各 testbench 不重新量化、不重新广播、不复制数据为另一套格式。SV 驱动可直接按16个字段 `$fscanf`，A/B须使用按 k_fp16 展开的packed向量而非32位integer。valid/气泡/reset 由测试调度控制，与数值向量分离；每个请求只在三路共同握手后推进读取位置。

## 期望、来源及再生

- `expected.jsonl`：id、d（8hex）、d_datatype、last 为有限位宽 DUT 逐位期望；exact_fp32_or_int32 为独立精确数学参考，fp64_tf32 为TF32近似参考或null。
- `source_reference.txt`：仅九种旧格式保留的原FP64 golden，作为来源证据，不作为新版逐位验收目标。
- `manifest.json`：schema、类型、两个K、请求数、来源路径及SHA256、五个数据段、golden配置/源码指纹、期望文件校验和。源码指纹排除build/。

九种旧格式的 correct_961 按原顺序保留 random64、mixed128、AI256、AI512、ones1；没有再次复制包含在其中的 batch512。历史来源记录在各数据 manifest 中。重新导入时通过 `test/cases/import_legacy.py --source-root` 指定原始 corpus，导入不写回来源。

TF32/INT8 generated_v1 使用种子20271104；编码随机、有限数/累加边界、定向极值及ones分别列段。先完成原九格式，再生成并验证这两种扩展。

```sh
python3 test/cases/import_legacy.py
python3 test/run_cmodel.py --phase existing --write-goldens
python3 test/cases/generate_extensions.py
python3 test/run_cmodel.py --phase extensions --write-goldens
```

`--write-goldens` 仅在独立参考检查通过后写期望；普通回归同时校验已保存期望和manifest。大量逐例诊断/trace位于忽略提交的 `test/runs/`。当前所有输入文件各自小于5MiB，提交的是精选可复用数据集，不是大规模原始仿真产物。

## 逻辑 K 扩展数据 dp_logical_vectors_v1

这批数据用于待 review 的混合 DP 架构，保存实际逻辑维度和精确数学结果，不声明新 CModel/RTL 已实现。输入为 `inputs.jsonl`，不会被现用 `inputs.txt` 回归入口读入。不得将 E96/E128 映射成虚假的全精度 `K_FP16=24/32`；后续混合顶层适配器负责把逻辑 group 按具体 profile 映射到物理端口。

| 原始 ratio 目录 | 格式 | 目标目录 | 每种笔数 |
| --- | --- | --- | --- |
| petile_full16_fp48 | MXFP4 E2M1、NVFP4、HiF4 | `dp/<format>/K96/petile_fp48_native_961/` | 961 |
| petile_full16_fp416 | MXFP4 E2M1、NVFP4、HiF4 | `dp/<format>/K128/petile_fp416_native_961/` | 961 |
| petile_full16_low16 | MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3 | `dp/<format>/K64/petile_low16_native_961/` | 961 |

共10套、9610笔，全部保留来源原生 K；本项目不截取、不使用 `petile_full16_fp432`。每套顺序为 batch64_random、batch128_mixed_random、batch256_deepseek_ai_load、batch512_ai_load、ones。原生 K96 的上游 metadata 记录其早期派生关系，本次读取的是用户指定 fp48 已有完整数据及重新计算的上游 golden；源 metadata 的 SHA-256 一并保留。

`inputs.jsonl` 每行仍包含上面16个具名字段；id 从0连续编号，last 为 JSON 布尔且仅最后一笔为 true。所有 packed 字段使用定宽小写 hex，低索引元素位于低位。Q 格式每元素占8位（FP6左移2位），E 格式每元素4位。令 `G=logical_k/8`（Q）或 `logical_k/16`（E），则 A/B 各占 `64G` 位、scale 各 `8G` 位、e1 各 `4G` 位、e2 各 `2G` 位、C固定32位。非 HiF4 的 e1/e2 为全零。相同 datatype 的 A/B 配对，C 为 FP32。

源 scale 文件包含未使用槽位，不能直接复制成每 group 的 scale。每个同类型连续物理区域以至多4个 group 分块：块首槽位为 B，局部组号为 g；Q/HiF4 选 `B`，MXFP4 选 `B+floor(g/2)`，NVFP4 选 `B+g`，然后按 group 重新展开。E96 的 MXFP4 索引为 `[0,0,1,1,4,4]`、HiF4 为 `[0,0,0,0,4,4]`、NVFP4 为 `[0,1,2,3,4,5]`。这保证最后两个 HiF4 group 保持原 K64 scale 共享语义。Q64 的索引为 `[0,0,0,0,4,4,4,4]`。各 manifest 保存具体索引；源 enum 和 DP enum 分开转换。

HiF4 e1 每4元素、e2 每8元素直接保留，C原位保留并只累加一次。NVFP4 scale 为正 E4M3 幅值，bit7不参与符号；导入检查来源未设置该位，独立参考亦按无符号合同处理。NaN/Inf、0×Inf、异号Inf及负零由独立格式语义处理，不能用机器浮点 NaN 比较替代数值分类。

- `expected.jsonl` 保存 `exact_fp32_or_int32`（一次精确到FP32 RNE的8hex结果）和 `exact_value`（有限数分子/分母字符串、分类、符号、invalid）。`d=null`、`cmodel_result=null`、`cmodel_status="not_implemented"`，明确没有有限位宽 DUT 期望。
- `source_reference.jsonl` 保存源段名/行号、原生K、上游FP64→FP32结果及重算的精确结果。源模型是 `fp64_dequant_dot_plus_c_v1`，不作为数学真值。8笔二次舍入差异见 [核验报告](../results/mixed-dp-data-20261107.md)。
- `manifest.json` 保存独立 schema、逻辑K、逐字段位宽、数据段/种子、源仓库HEAD、相对源路径、全部源文件SHA-256、参考代码SHA-256及产物校验和。生成语料可能不在上游Git内，因此内容hash优先于HEAD；CModel/RTL均为未实现，PPA资格为false。

从仓库根目录执行；来源只读，实际源目录由本机环境提供：

```sh
python3.11 test/cases/import_petile_ratio.py \
  --source-root /path/to/Quant_LLM_Chip_Codesign/HW/tests/data/petile_test_data/petile_ratio
python3.11 -m unittest discover -s test/tests -p test_logical_vectors.py -v
```

`--dest-root /tmp/dp-logical-replay` 可在独立目录重建同一批数据，逐文件比较校验和。重新生成仅允许覆盖 schema、format、K 相同的逻辑数据集；现用961基线及其 CModel 期望保持不变。
