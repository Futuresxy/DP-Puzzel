# hw：单阵列 / 单计算核心

本部分提供真实硬件实现与测量证据，范围止于一个计算阵列或一个计算核心，不实现整颗多核心芯片。

| 目录 | 责任 | 不负责 |
| --- | --- | --- |
| spec | 格式、缩放、累加、接口、流水、数据流和验收 | 芯片配比搜索 |
| configs | 单阵列/单核参数与支持模式 | 芯片级阵列数量 |
| chisel_src | 可综合的单阵列/单核设计及必要转换/缩放逻辑 | 全芯片调度 |
| rtl | 每次导出的唯一设计文件和来源记录 | 手工修补 RTL |
| test | Verilog/SystemVerilog testbench 精度和周期验证 | 以 Chisel 测试替代最终验证 |
| dc_syn | 挂载 EDA 中的 DC 综合、面积和时序 | 无库条件下伪造面积 |
| power | 同一硬件在真实负载与 idle 等状态下的活动和功耗 | 用随机 smoke 活动代替真实负载 |
| characterization | 发布可追溯 profile、适用范围和误差 | 无来源地外推整芯片功耗 |

主流程：spec → 参数 → Chisel → 唯一 RTL → RTL testbench → DC/时序 → 真实负载活动/功耗 → 硬件特征。

单核 profile 必须列明是否包含 L0、阵列、缩放/转换、控制等，供芯片模型避免重复计费。阵列共享多个数值模式时，物理实现只计一次面积，每种模式分别测量性能和活动成本。

当前优先迁移 full 四层复用基线 `SubPE → PEGroupFull → MidGroupFull → PETile`，见 [逐文件导航](chisel_src/README.md) 和 [full 迁移](spec/full-reuse-migration.md)。通过 [集中配置](configs/README.md) 的 mid_groups/align_width 改变完整 MidGroup 数和对齐窗口。此前扁平 PE/MN-PE/K-PE 已移出工作树，可从 Git 历史追溯。Scala/Chisel/导出工具版本固定；没有 RTL 数值通过证据或测量数据。阵列组织、工艺和目标频率后续确定。
