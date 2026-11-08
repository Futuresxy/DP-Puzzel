> 功能：六种现用 DP 的可编辑嵌套架构图入口；范围：top/group/lane 归属、S1–S8 主要计算和精度参与；版本：v1.7.8；修改时间：2026-11-08 18:45:29 +08:00；对应代码：src/verilog/top/、src/verilog/group/、src/verilog/lane/ 及 top/common/ 的现用纯 Verilog。

# 六种 DP 可编辑架构图

本目录交付六个独立的原生 `.drawio` 文件，直接用 diagrams.net 或 VS Code Draw.io 编辑器打开。框、文字、寄存边界和连线均为可编辑对象；没有嵌入整张图片。图内仅保留功能名、级号、实例数量及选择条件，不展开位宽或计算公式。沿用原图的米白顶层、灰色 lane、蓝色解包、红色乘法、紫色移位、绿色符号处理和黄色规约配色。

| 架构 / H:Q:E 容量比 | draw.io 源文件 | 每个 DP 的 group 组成 | S6 源数（含一份 C） |
| --- | --- | --- | ---: |
| T8H16Q32E64 / 1:2:4 | [dp_arch.drawio](dp_arch.drawio) | 4 × dp_group | 5 |
| T8H16Q32E96 / 1:2:6 | [dp_top_t8h16q32e96.drawio](dp_top_t8h16q32e96.drawio) | 4 × dp_group + 2 × dp_group_e | 7 |
| T8H16Q32E128 / 1:2:8 | [dp_top_t8h16q32e128.drawio](dp_top_t8h16q32e128.drawio) | 4 × dp_group + 4 × dp_group_e | 9 |
| T8H16Q64E128 / 1:4:8 | [dp_top_t8h16q64e128_opt.drawio](dp_top_t8h16q64e128_opt.drawio) | 4 × dp_group + 4 × dp_group_qe（紧凑版） | 9 |
| E64 / 0:0:1 | [dp_top_e64.drawio](dp_top_e64.drawio) | 4 × dp_group_e | 5 |
| Q32E64 / 0:1:2 | [dp_top_q32e64.drawio](dp_top_q32e64.drawio) | 4 × dp_group_qe（紧凑版） | 5 |

比例表示各模式的原生容量，不是同时工作的多种精度；T=TF32，H=FP16/BF16，Q=MXFP8/6，E=MXFP4/NVFP4/HiF4。基线及三个混合架构保留基础支 INT8 K32，E/QE 专用组不支持 INT8。`dp_top_e` 是兼容入口，不另算第七种架构。

## 如何阅读和编辑

- 外框是完整 DP；混合/低精度包装的 `u_core` 实现名标在顶部，不额外增加流水。
- 叠层框表示独立并行的重复 group，数量由 `×N` 标明。每种 group 展开一个代表，内部明确画出两条独立 lane；不把所有重复 group 平铺。group 是 lane 和组内运算框的真实 XML 父容器，移动前景 group 时内部图元随之移动；背后的叠层轮廓只是重复数量示意。
- 数据解包位于 lane 内；scale 解包、公共指数与组级 scale 乘法位于 group 内。彩色功能框表示主要组合功能分区，不保证每个框都对应单独 RTL module。原生模块及复用核心的源码映射见[六种架构说明](../dptop/top-architectures.md)。
- `rN` 条表示流水寄存边界。多精度/QE 的 lane 保存 r1–r4，S5 组和/abs/scale/LZD；E lane 只保存 r1–r3，S4 出口小移位和组和/abs 由 group r4 捕获，S5 scale/LZD。所有图仍为 L8/II=1。
- lane 中以 Mode MUX → Shared MUL 表示按精度复用乘法资源；S3 将直接乘积或 E Pair 经 MUX 送入同一个 Shift，再恢复符号，共用 S4 Reduce Tree。INT8 的 S3 是静态落位和零移位量，不画成不存在的独立移位旁路。
- S2 公共 MAX 是同拍组合反馈到两条 lane 的指数旁路，不是额外握手或新增流水。E 专用组没有元素指数 MAX / 跨 lane 右移，HiF4 e2 在 lane 出口融合。
- S5 的 NVFP4/HiF4 使用 **14×8 无符号 scale 乘法**，符号独立同行；LZD 只计数，不在此处做规格化移位。E 专用 HiF4 与多精度/QE 的 token 坐标可不同，由 magnitude/A_raw/z 表达同一数值。
- C 在顶层独立保存，S5 解包，S6 与各组共同对齐，S7 只加入一次。S6 明确画出浮点双向移位与 INT Placement 两路，经 FP/INT MUX 后恢复符号；S8 的 INT32 Wrap 绕过浮点规格化与舍入，经输出 MUX 选择。E64/Q32E64 不画整数路径。
- 混合架构的扩展参与位随请求传递；不支持的格式关闭扩展数据使能，并从 MAX、求和、特殊值归约中屏蔽扩展贡献。S6 以 MAX / Base Bypass 选择全局指数；S7 画出 Ext/0 MUX、扩展树、Merge ADD 和 Merged/Base MUX。扩展关闭时直通基础和，**基础树仍含 C，不旁路 C**。ext_active 表示 MAX 中有效非零扩展源，图中的 E enable / Q/E enable 对应 ext_en，表示该请求的格式参与资格，两者含义不同。

图纸对应默认 K_FP16=16、LOCAL_W=28、GLOBAL_W=40。功能图不代表每个 MUX 都综合成独立单元，也不是新时序或功耗证据；本次只更新可编辑文档，不改 RTL / CModel。

计算细节分别见[流水合同](../dptop/pipeline.md)、[E lane](../lane/dp_lane_E.md)、[E group](../group/dp_group_E.md)、[QE lane](../lane/dp_lane_qe.md)、[QE group](../group/dp_group_qe.md)与[全局对齐](../dptop/global-align.md)。当前测量数据仍由[综合索引](../../../../hw/dc_syn/records/latest_six_dp.md)和[功耗汇总](../../../../hw/power/records/current_six_precision_gated.md)管理。
