# DP 共用测试数据：DP_INPUTS_V1

功能：保存可由 CModel、Chisel 生成 RTL、手写 Verilog 共用的 packed 端口数据。版本 v1.0；2026-11-04；对应 DP spec v1.4，代码 [适配器](../adapters/cmodel.py)。当前已验证 CModel，RTL TB 尚未实现。

目录 `dp/<format>/K<logical_k>/<dataset>/` 的 K 是该格式的实际元素数。各 manifest 中 k_fp16 是硬件基准 K，两者不能混用。当前主数据全部 k_fp16=16，因此 T8/H16/Q32/E64/INT32项。

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
