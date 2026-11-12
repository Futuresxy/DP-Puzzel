# QE 扩展 v1.12 功能验收（2026-11-12）

两个固定新顶层采用四个基础组加 8/12 个紧凑 QE 组，形成 T8H16Q96E192 / T8H16Q128E256。S6 同周期 MAX 和各组移位；S7 扩展支采用 3/5 个 CSA4:2，保留双行到片选后唯一 CPA。L8、II=1，默认 S44/S45。

**完整 DP 保留原 T8/H16 基础能力：TF32、FP16、BF16 和 INT8 只激活原四个多精度组；Q/E 激活全部 12/16 组。新增组为 QE 扩展支，并非将顶层替换为纯 Q/E DP。**

11 格式原生 RTL 回归包含每种顶层的 TF32 1053 笔、FP16 961 笔、BF16 961 笔及 INT8 1045 笔，均逐位匹配冻结模型；另包含四种 Q 和三种 E 的各 961 笔原生数据。

此回执来自隔离副本 `hw/power/runs/qe_expansion_source_1112/`；以下链接相对此副本根目录。主项目整合后的 current-source 门禁须另行完成。

| profile | export | 原生数值笔数 | campaign | S2–S7断点 |
|---|---|---:|---:|---:|
| t8h16q96e192 | DP_verilog_t8h16q96e192_1e63c2625d0dd101 | 10747 | 14 | 2819997 |
| t8h16q128e256 | DP_verilog_t8h16q128e256_f8209095129aa89a | 10747 | 14 | 3754053 |

CModel 完整 52 项通过；扩展配置与有限窗/CSA 专项在完整回归结束后串行重验 2 项通过。DC 流程 45 项、功耗流程 74 项通过（1 项依赖缺失跳过）。Q96/Q128 的四种 Q 格式与 E192/E256 的三种 E 格式使用各自原生 961 笔语料，输入 hash 和独立精确数学参考全部核验。

RTL 三个窗口为 LOCAL/GLOBAL=27/40、28/40、32/64；每个窗口含逐拍换型、气泡、复位取消、失活组毒化、Q32/MX32/NV16/HiF64 scale 边界、每个物理组单独贡献及跨四叶 CSA 边界抵消。每种精度都对比冻结模型位结果，并保留与精确数学参考的 ULP 区别。

六份真实功耗输入各 1024 笔，其派生模型结果全部与独立精确数学参考一致；这不代替门级重放或实测功耗。

- `t8h16q96e192` 回执：`test/runs/verilog/20261112T122236879949Z/verification.json`；SHA-256 `491accd014d1efe649b9a7fd119ef02975c413bfd930ea53977f9bbdcc6ddd1e`。
- `t8h16q128e256` 回执：`test/runs/verilog/20261112T122135109358Z/verification.json`；SHA-256 `b1ee87db36ffbc1015649ee4dfbc0199c04c7bad65f38ff26b03128c652fb4f9`。

DC 已按 N12 TT/0.7V/85°C、1GHz、ICG 开启独立启动。此功能回执不宣称时序或功耗验收通过；数值与周期验证不能替代 DC/Power Compiler 测量。

## 独立 Fraction 精确审查

父 agent 另行编写确定性 238 笔检查，两 profile 均与 Fraction 精确参考一致；源码、输入、结果和配置作为辅助证据追加到原验证 run，原验证回执不改写。

- `DP_verilog_t8h16q96e192_1e63c2625d0dd101`：`test/runs/verilog/20261112T122236879949Z/auxiliary/qe_independent_review_1112/review.json`，SHA-256 `9e1b3703f36bff611594f65bcd1ff1478fa8d982745340d9b0985b78b950fead`。
- `DP_verilog_t8h16q128e256_f8209095129aa89a`：`test/runs/verilog/20261112T122135109358Z/auxiliary/qe_independent_review_1112/review.json`，SHA-256 `9e1b3703f36bff611594f65bcd1ff1478fa8d982745340d9b0985b78b950fead`。
