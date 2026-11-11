# 混合 DP 逻辑数据与精确 golden：2026-11-07

本批只准备架构讨论所需的数据和数学参考，没有新增混合 CModel/RTL、运行 DC 或测量功耗。基线 `feat/dp-verilog-v14` 的 `9af0259`；新增数据使用 `dp_logical_vectors_v1`，不进入现有 `DP_INPUTS_V1` 的10747笔回归。来源、布局和再生入口见 [数据说明](../data/README.md#逻辑-k-扩展数据-dp_logical_vectors_v1)。

## 原生数据导入

源仓库 `Quant_LLM_Chip_Codesign` 的读取时 HEAD 为 `5a5037ad03b656ea975ef594d0aca4dc5ef96a39`。读取其相对路径 `HW/tests/data/petile_test_data/petile_ratio/`；各 manifest 保存源 metadata、输入和上游 golden 的逐文件 SHA-256，不能仅凭 HEAD 定位生成语料。

| 源 ratio | 实际每侧16位 word数 / K | 格式 | 数量 |
| --- | --- | --- | --- |
| petile_full16_fp48 | 24 / E96 | MXFP4 E2M1、NVFP4、HiF4 | 3×961 |
| petile_full16_fp416 | 32 / E128 | MXFP4 E2M1、NVFP4、HiF4 | 3×961 |
| petile_full16_low16 | 32 / Q64 | MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3 | 4×961 |

共10套、9610笔；每套64随机+128混合随机+256 DeepSeek负载+512 AI负载+1 ones。本项目未截取源K，未读取 fp432。fp48 源 metadata 已记录其由 fp416 派生的上游关系；此处直接读取用户指定的现有原生 K96 文件及上游重算 golden。

A/B元素顺序不变，FP6从每byte低6位搬到高6位；稀疏 scale 槽展开为每个 Q8/E16 group 一字节，HiF4 e1/e2按每4/8元素保留，C保留原FP32并仅加一次。K96最后两个HiF4组继续共享对应上游K64尺度。源 scale 类型与 DP enum 显式转换，NVFP4 scale 的符号位未设置，按无符号幅值解释。

`expected.jsonl` 保存 Fraction 精确值/分类及一次 FP32 RNE 的结果。有限位宽 CModel结果 `d`/`cmodel_result` 为null，CModel/RTL状态均为 `not_implemented`，不伪造实现验收。各源数据的数学结果均从输入重新计算，未把上游FP64或硬件结果复制为真值。

## 上游 FP64 与精确参考的8笔差异

上游模型为 `fp64_dequant_dot_plus_c_v1`：binary64反量化、`math.fsum`规约所有乘积与C，再转FP32。本次精确有理数先求真实 dot+C，再一次舍入到FP32；9602/9610笔与上游逐位相同，剩余8笔均差1ULP，没有非有限结果不一致。

| 格式 / K | 全局id | 源段 / 段内索引 | 精确FP32 | 上游FP32 |
| --- | ---: | --- | --- | --- |
| MXFP4 E2M1 / 96 | 171 | batch128_mixed_random / 107 | ca8fffe9 | ca8fffe8 |
| MXFP6 E2M3 / 64 | 131 | batch128_mixed_random / 67 | c2ac6b53 | c2ac6b52 |
| MXFP6 E3M2 / 64 | 34 | batch64_random / 34 | e80dad2f | e80dad2e |
| MXFP6 E3M2 / 64 | 149 | batch128_mixed_random / 85 | c1df7d15 | c1df7d14 |
| MXFP8 E4M3 / 64 | 0 | batch64_random / 0 | c012e55f | c012e55e |
| MXFP8 E4M3 / 64 | 91 | batch128_mixed_random / 27 | c0156ad5 | c0156ad6 |
| MXFP8 E5M2 / 64 | 44 | batch64_random / 44 | c04c510b | c04c510c |
| MXFP8 E5M2 / 64 | 142 | batch128_mixed_random / 78 | 638f6bcf | 638f6bd0 |

这8笔都是可验证的二次舍入，不是数据映射或硬件截断误差。令精确有理数为x，两份FP32解码值为p、q；独立检查逐笔确认 `abs(x-p)<abs(x-q)`，同时 `Fraction.from_float(float(x))==(p+q)/2`，而上游q的尾数最低位为偶数。也就是说，binary64已经丢掉决定FP32舍入方向的微小余量，落到FP32中点，随后RNE选偶数邻值。直接精确舍入应选择严格更近的p。

这项检查使用Python `struct` 解码两份FP32和有理数距离，不调用本项目 `fp32()` 实现；可用下述 `test_upstream_fp64_rounding_differences` 重现全部8笔。完整分子/分母及来源行号已保存在各数据目录，避免仅保留文字解释。

## 验证与复现

```sh
python3.11 test/cases/import_petile_ratio.py \
  --source-root /path/to/Quant_LLM_Chip_Codesign/HW/tests/data/petile_test_data/petile_ratio
python3.11 -m unittest discover -s test/tests -p test_logical_vectors.py -v
```

通过10项测试：所有9610笔重新解码并重算精确 golden、源/目标K一致、全部产物及参考源码hash、manifest布局、FP6位置和稀疏scale、完整group及长度拒绝、ones和HiF4末组e1/e2、NaN/Inf/负零/无符号scale及C特殊值、8笔独立舍入证明，以及252笔现有合法参数随机向量与既有数学参考一致。

既有数据入口仍只读11套 `inputs.txt` 共10747笔，均为原 `k_fp16=16`，旧输入和golden未修改。重新生成到独立 `/tmp/dp-logical-replay` 后，40个产物逐文件SHA-256完全一致。总数据9,492,345字节，最大文件497,687字节，全部小于5MiB。

本批数据检查不替代后续新前端和混合top的数值、时序协议、门禁或PPA验证；不把数学golden生成成功写成新架构实现通过。
