> 功能：按模块与共用合同组织 DP 规格；范围：lane、group、dptop、多精度主实现及 E 类优化候选；版本：v1.7.7；修改时间：2026-11-08 09:41:42 +0800；对应代码：[dp_top.v](../../verilog/top/dp_top.v)、[CModel model.hpp](../../cmodel/include/dp/model.hpp)；E 专用 CModel 与 [dp_top_e.v](../../verilog/top/dp_top_e.v) 已实现，Chisel 尚未实现。

# DP 规格导航

**当前 dp_top 已批准架构为 [v1.8](dptop/dp-top-v1.8.md)，先更新规格，再实现 CModel/RTL 并验证；其他顶层仍为 v1.7。下列实现描述和旧 PPA 仅代表原快照。**

当前多精度主实现为 T8H16Q32E64、L8、II=1，默认局部/全局窗口 28/40；每笔完成 scaled_dot(A,B)+C，无跨请求累加状态。当前设计族架构 v1.7，实现映射 v1.7.1；原顶层容量不变，新增三个固定配比的混合顶层。

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
│   ├── dp_lane_E.md
│   └── dp_lane_qe.md
├── group/
│   ├── README.md
│   ├── shared-align.md
│   ├── scale.md
│   ├── dp_group_E.md
│   └── dp_group_qe.md
├── dptop/
│   ├── README.md
│   ├── module-hierarchy.md
│   ├── interface.md
│   ├── layout-and-scales.md
│   ├── control.md
│   ├── pipeline.md
│   ├── global-align.md
│   ├── independent-align.md
│   └── mixed-precision-expansion.md
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

[E8 lane 优化](lane/dp_lane_E.md) 与 [E16 group / E64 接入](group/dp_group_E.md) 已纳入对应模块目录。用户已明确 HiF4 e2 在 lane 内融合、先求和后局部左移、删除组内元素指数对齐，以及保持多精度 group 输出 layout 和 S5 到达拍。用户已选择优先讨论 E64 的 S2 乘法/pair、S3 四项 lane 树、S4 group 合并/abs、S5 scale/LZD 切分，专用 CModel 与 RTL 已实现并通过测试；面积/时序见 [同工况 DC 对比](../../../hw/dc_syn/records/README.md#历史记录)。

E 专用候选通过兼容 token 接入既有 S6–S8；默认保留 40 位全局窗口。HiF4 融合 e2 后的定点坐标及 anchor/z 换算以专用 group 文档为准，不能套用多精度主实现的逐级字段值。

## 4. 当前实现边界

主实现 S1 解包 → S2 元素乘法/指数 MAX → S3 局部对齐/E pair → S4 lane 树 → S5 组和/abs/无符号 scale/LZD 及 C 解包 → S6 一次双向对齐 → S7 总树 → S8 FP32 RNE 或 INT32 回绕。[八级架构图](draw.io/dp_arch.drawio)

A/B 同格式，合法请求可逐拍换型；last 只透传，无输出背压，全局复位取消在途请求。默认 L8，L9 为静态备用探索。独立整体对齐、Chisel 和阵列尚未实现；频率与功耗结论必须关联实际冻结输入与测量证据。

## 5. 不同 DP 类型的项目框架建议

将多精度与 E 专用组织为同一设计族：共用基础库，lane/group 内区分 multi/e，dptop 复用后端并按静态 profile 装配。当前模块目录保持功能分层；变体增加后可在 lane/group 内分别建立 multi/e 子目录，共用数值合同与 scale/后端说明只维护一份，各类型文档记录自身的数据通路、S/I/F、周期和适用范围。

建议的配置、能力矩阵及组合边界见 [模块层级第 9 节](dptop/module-hierarchy.md#9-dp-设计族的工程组织建议)，源码目标布局分别见 [RTL](implementation/verilog.md#6-分类型模块与组合配置建议) 与 [CModel](implementation/cmodel.md#7-与-rtl-对应的设计族组织建议)。CModel 已新增 lane/lane_e.cpp、group/group_e.cpp，抽取 top/backend.cpp，接入 src/configs/dp/e64.json；RTL 增加 dp_lane_e/dp_group_e/dp_top_e 和 files_e.f；原多精度顶层保留，三个固定混合 profile 已实现，未提供任意 group 装配接口。默认多精度请求和数值接口保持兼容。

## 6. 混合组扩展：v1.7.1

[混合顶层合同](dptop/mixed-precision-expansion.md) 定义保留四个多精度组后，新增 2/4 个 E 组形成 T8H16Q32E96/E128，或新增四个 [QE group](group/dp_group_qe.md) / [QE lane](lane/dp_lane_qe.md) 形成 T8H16Q64E128。后端按请求屏蔽扩展支的 MAX、移位、求和与特殊值，保持单次 C 和 L8/II=1。

CModel 和 QE/混合 Verilog 已实现；三个顶层分别通过完整 Verilator 验证，保持 L8/II=1。同库同约束 N12 TT/1GHz 综合已完成，保持 L8/II=1，setup/hold/VT/电气规则均通过；面积、门控及各级时序见 [实测比较](../../../hw/dc_syn/records/README.md#历史记录)。

## 7. 面积优化方案与证据边界

[混合顶层第 10 节](dptop/mixed-precision-expansion.md#10-独立面积优化版本与验收)记录 Q64E128 的 +80.64% 面积来源、+55%–65% 目标、拟建独立优化版本和验收条件；实现细节分别归属 QE/E lane 与 group。首轮优化实现修订为 v1.7.3；独立优化顶层及原顶层已通过 [功能验证](../../../test/results/qe-area-opt-v1.7.3.md)，[新快照 DC 验收](../../../hw/dc_syn/records/README.md#历史记录)已通过 1GHz，面积增幅由 80.64% 降至 66.53%，用户接受本轮结果；历史 PPA 仍对应原快照。

扩展 QE 保留四种 MXFP8/6 与 MXFP4/NVFP4/HiF4，扩展 E 保留三种 E；只有基础四组支持 T/H/INT8。优先优化固定字段解包、分类/符号寄存和扩展源整数选择，默认窗口 28/40、L8/II=1、单次 C 与数值行为保持。未测的面积节省和功耗收益不写入实测结论。
