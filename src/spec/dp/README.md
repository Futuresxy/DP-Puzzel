> 功能：按模块与共用合同组织 DP 规格；范围：lane、group、dptop、多精度主实现及 E 类优化候选；版本：v1.6；修改时间：2026-11-06 12:06:08 +08:00；对应代码：[dp_top.v](../../verilog/top/dp_top.v)、[CModel model.hpp](../../cmodel/include/dp/model.hpp)；E 专用 CModel 与 [dp_top_e.v](../../verilog/top/dp_top_e.v) 已实现，Chisel 尚未实现。

# DP 规格导航

当前多精度主实现为 T8H16Q32E64、L8、II=1，默认局部/全局窗口 28/40；每笔完成 scaled_dot(A,B)+C，无跨请求累加状态。当前架构 v1.5，实现映射 v1.5.1。本文档目录调整不改变算术、接口、流水或验证结论。

## 1. 按模块查找

| 模块层级 | 容量与阶段 | 设计入口 | 内部计算设计 |
| --- | --- | --- | --- |
| lane | T1H2Q4E8；主实现 S1–S4 | [lane/README.md](lane/README.md) | 元素解包、尾数乘法共享、局部移位、lane 规约、E8 优化 |
| group | T2H4Q8E16；两 lane 协作及 S5 | [group/README.md](group/README.md) | 公共指数、组和、符号/幅值、scale 乘法、LZD、E16 优化 |
| dptop | G 个组+C；请求控制及 S5–S8 | [dptop/README.md](dptop/README.md) | 输入分发、C 解包、组间对齐、最终树、FP32/INT32 输出 |

T=TF32，H=FP16/BF16，Q=MXFP8/6，E=MXFP4/NVFP4/HiF4；INT8 与 Q 同并行度。G=K_FP16/4，K4/K8/K16 对应 1/2/4 个基本组。三个层级分工于同一次八级计算，不是各串联八级。

~~~text
dp/
├── README.md
├── lane/
│   ├── README.md
│   ├── unpack.md
│   ├── multiplier-sharing.md
│   ├── shifter-sharing.md
│   └── dp_lane_E.md
├── group/
│   ├── README.md
│   ├── shared-align.md
│   ├── scale.md
│   └── dp_group_E.md
├── dptop/
│   ├── README.md
│   ├── module-hierarchy.md
│   ├── interface.md
│   ├── layout-and-scales.md
│   ├── control.md
│   ├── pipeline.md
│   ├── global-align.md
│   └── independent-align.md
├── common/             # 跨层数值合同
├── implementation/     # 模型、RTL 验证与资源统计
└── draw.io/            # 架构图源码
~~~

## 2. 跨层合同和实现验证

| 分类 | 文档 | 维护边界 |
| --- | --- | --- |
| 参数与定点推导 | [common/numeric-layout.md](common/numeric-layout.md) | 全部层级共用的位宽、符号表示和 anchor 公式 |
| S1–S8 出口 | [common/stage-formats.md](common/stage-formats.md) | 多精度主实现的逐级 S/I/F 与指数范围 |
| 特殊值和舍入 | [common/special-values.md](common/special-values.md) | NaN/Inf/零/非正规及 FP32 RNE |
| CModel | [implementation/cmodel.md](implementation/cmodel.md) | 位精确与周期模型、参考和 trace |
| Verilog | [implementation/verilog.md](implementation/verilog.md) | 现用 Verilog 映射、快照与验证门禁；SV 为冻结参考 |
| 面积/功耗统计 | [implementation/resource-accounting.md](implementation/resource-accounting.md) | 逻辑块、寄存/mux、网表与活动统计归属 |

跨层合同集中维护，不在 lane/group/dptop 重复定义同一套位宽公式。scale 运算由 group 拥有，S6 双向移位由 dptop 拥有；两者分别链接到共用数值坐标。

## 3. E 类优化方案入口

[E8 lane 优化](lane/dp_lane_E.md) 与 [E16 group / E64 接入](group/dp_group_E.md) 已纳入对应模块目录。用户已明确 HiF4 e2 在 lane 内融合、先求和后局部左移、删除组内元素指数对齐，以及保持多精度 group 输出 layout 和 S5 到达拍。用户已选择优先讨论 E64 的 S2 乘法/pair、S3 四项 lane 树、S4 group 合并/abs、S5 scale/LZD 切分，专用 CModel 与 RTL 已实现并通过测试；面积/时序见 [同工况 DC 对比](../../../hw/dc_syn/records/e64_n12_comparison_20261105.md)。

E 专用候选通过兼容 token 接入既有 S6–S8；默认保留 40 位全局窗口。HiF4 融合 e2 后的定点坐标及 anchor/z 换算以专用 group 文档为准，不能套用多精度主实现的逐级字段值。

## 4. 当前实现边界

主实现 S1 解包 → S2 元素乘法/指数 MAX → S3 局部对齐/E pair → S4 lane 树 → S5 组和/abs/无符号 scale/LZD 及 C 解包 → S6 一次双向对齐 → S7 总树 → S8 FP32 RNE 或 INT32 回绕。[八级架构图](draw.io/dp_arch.drawio)

A/B 同格式，合法请求可逐拍换型；last 只透传，无输出背压，全局复位取消在途请求。默认 L8，L9 为静态备用探索。独立整体对齐、Chisel 和阵列尚未实现；频率与功耗结论必须关联实际冻结输入与测量证据。

## 5. 不同 DP 类型的项目框架建议

将多精度与 E 专用组织为同一设计族：共用基础库，lane/group 内区分 multi/e，dptop 复用后端并按静态 profile 装配。当前模块目录保持功能分层；变体增加后可在 lane/group 内分别建立 multi/e 子目录，共用数值合同与 scale/后端说明只维护一份，各类型文档记录自身的数据通路、S/I/F、周期和适用范围。

建议的配置、能力矩阵及组合边界见 [模块层级第 9 节](dptop/module-hierarchy.md#9-dp-设计族的工程组织建议)，源码目标布局分别见 [RTL](implementation/verilog.md#6-分类型模块与组合配置建议) 与 [CModel](implementation/cmodel.md#7-与-rtl-对应的设计族组织建议)。CModel 已新增 lane/lane_e.cpp、group/group_e.cpp，抽取 top/backend.cpp，接入 src/configs/dp/e64.json；RTL 增加 dp_lane_e/dp_group_e/dp_top_e 和 files_e.f；原多精度顶层保留，通用混合组配置仍是讨论稿。默认多精度请求和数值接口保持兼容。
