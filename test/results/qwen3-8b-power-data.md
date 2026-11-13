# Qwen3-8B MLP 功耗输入准备

日期：2026-11-08；范围：数据提取、精确数学参考、CModel输出和首批功耗计划。没有执行本次负载的RTL/VCS门级验证，没有生成SAIF，没有测量功耗。

来源：Quant_LLM_Chip_Codesign 的 `HW/tests/data/petile_test_data/power_data/PETileRatio_Qwen8BMLPPower_1027202452/petile_ratio`；dataset为`batch1024_qwen3_8b_layer0_mlp_down_proj`。每套manifest保存来源仓库版本、源文件/样本校验和、量化策略和C语义，来源只读。

| 精度 | K | 套数 | 数学参考笔数 | CModel计算次数 |
| --- | --- | ---: | ---: | ---: |
| BF16、FP16 | 16 | 2 | 2048 | 8192 |
| MXFP8 E4M3、E5M2 | 32、64 | 4 | 4096 | 10240 |
| MXFP4 E2M1、NVFP4、HiF4 | 64、96、128 | 9 | 9216 | 18432 |
| 合计 | | 15 | 15360 | 36864 |

15360笔Fraction精确解码、点积加C、一次FP32 RNE与上游FP64参考的FP32编码全部一致。36864次六架构适用的CModel计算全部与精确结果一致，max ULP=0、超过4 ULP数量0。CModel和RTL门级结果的验收仍必须逐位一致，不能用该数学误差统计替代门级验证。

测试覆盖15套输入/期望校验和、1024笔连续ID及last、跨格式共享C、同格式跨K的数据/scale/HiF4元数据前缀一致性，并从已落盘packed输入重新计算全部精确有理数和FP32结果。3项测试通过。无源码RTL变更；用户的dp_group.v未提交排版改动保留。

复现：

```bash
# 先按src/cmodel/README.md构建dp_cmodel_cli。
python3.11 test/cases/import_qwen_power.py \
  --source-root /path/to/PETileRatio_Qwen8BMLPPower_1027202452/petile_ratio \
  --summary test/results/qwen3-8b-power-data.json
python3.11 -m unittest discover -s test/tests -p test_qwen_power_data.py -v
python3.11 hw/power/scripts/prepare_qwen_plan.py \
  --output hw/power/plans/qwen3_8b_first3.json
```

导入器拒绝覆盖内容不同的既有数据集；同版本同来源重放可复核。输入保存于`test/data/power/<format>/K<logical_k>/qwen3_8b_mlp_down_proj_1024/`。H类用原DP_INPUTS_V1，Q/E沿用logical K schema。expected同时保存按frontend区分的CModel结果和精确数学结果，不把来源FP64值直接用作DUT逐位golden。

统计：[JSON摘要](qwen3-8b-power-data.json)。后续：[功耗程序搭建方案](../../hw/power/implementation-plan.md)。
