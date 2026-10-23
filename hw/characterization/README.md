# hw → ratio_dse 的硬件特征边界

只发布有来源、单位、适用范围和验证状态的小型 profile。完整契约见 [数据契约](../../docs/data-contracts.md)。

profile 区分 array/core，绑定 hardware/config/export/RTL-verification/DC/power 的 ID 与 hash，声明包含的阵列、L0、控制、转换/缩放等组件。包含整个 core 的 profile 不能再与其内部 array 面积叠加。

性能应含各数值模式的吞吐、latency、II、fill/drain、目标/达成频率。面积附库/PVT和时序证据。功耗附真实 workload/活动窗口、active/idle 等状态、覆盖率与工具版本。可扩展活动计数到功耗的拟合模型，但必须保存校准与留出验证误差。

未知值为未测量，不能填零。先只有解析估算的 profile 必须独立标记，不能冒充 measured/calibrated。正式结果必须能沿来源链恢复同一份 RTL 与测量条件。

后续将放置 schema、精简 profile 和索引；当前无测量文件。
