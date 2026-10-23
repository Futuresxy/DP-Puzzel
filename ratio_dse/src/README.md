# 模型组件与后续文件职责

当前只定义逻辑模块；没有代码。文件名是实施阶段的建议，语言与拆分方式可在接口稳定后确认。

| 拟定组件/文件 | 职责 | 输入 → 输出 |
| --- | --- | --- |
| formats | 解析格式语义和转换/缩放需求 | FormatSpec → 模式约束与有效存储成本 |
| profiles | 加载、校验和索引硬件证据 | HardwareProfile → 带范围/工况的成本接口 |
| chip | 物理实例、层级与共享关系 | ChipConfig → 资源图和模式能力 |
| workload | GEMM/依赖/精度资格规范化 | WorkloadSpec → 任务图 |
| mapping | tiling、K 分割、阵列/核心划分 | 任务与资源 → 映射候选和数据需求 |
| memory | HBM/L1/L0 容量、带宽、复用与争用 | 移动请求 → 资源约束与字节/访问统计 |
| scheduling | 多核心并发、互斥、同步、重叠 | 映射与资源 → 执行时间线/活动 |
| latency | 统计完成时间、关键路径和瓶颈 | 时间线 → GEMM latency 分解 |
| area | 不重不漏地组合物理成本 | 资源与 profile → 芯片面积分解 |
| power | 将活动与真实负载校准成本组合 | 时间线、profile、存储成本 → 功耗分解 |
| search | 枚举/搜索候选、预算过滤、多目标比较 | Scenario → 可行集与 Pareto |
| reporting | 可追溯汇总和论文数据导出 | 指标与证据 → 小型摘要/图表输入 |
| adapters | CACTI 等外部模型的协议与单位接入 | 固定依赖与配置 → 规范化模型数据 |

mapping 不自行伪造功耗，area 不推导 workload latency，search 不绕过底层可行性。不同模块之间按 docs/data-contracts.md 交付，避免一份脚本同时隐式改变映射、成本和优化目标。
