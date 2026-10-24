# 真实负载选择与 RTL 测试数据

canonical输入、独立golden、scale/C策略、事务时序及参考RTL testbench由`hw/test`及其回归流程维护。具体数据/testbench位置由用户后续明确，当前`test_bindings`为pending/null；不把目录惯例当作已存在的数据集。这里仅保存selector，不复制tensor、向量、golden或设计RTL。

正式 selector 需要 dataset manifest/path/hash、export/verification ID、格式/模式、真实片段或 task ID、顺序区间和边界定义，字段见 [输入契约](../input-contract.md)。它必须证明所选数据确实被相应 RTL 验证覆盖，不能只取文件名近似的数据。

保留握手、气泡、stall、K 分块累加和原始权重复用。新增片段先在测试侧版本化并回归；数据不足时不能由功耗侧随机补齐。源测试未包含真实调度时，保持 continuous-compute 标签，不能伪造 task trace。

当前K-PE/MN-PE selector固定选择`96×1024 = 98304`对有效标量A/B数据，计98304 MAC；H16/Q32/E64分别需6144/3072/1536次完整有效调用。每个候选按整个DUT的满调用容量检查整除，不允许partial tail、padding或取整；MN-PE并行输出按实际有效配对汇总，不把数据广播或同一输入值复用误当唯一源样本增长。每调用容量、任务总K、准备调用与计数burst分别记录，保留源序列/累加依赖。

绑定后参考所选RTL testbench复用driver、时钟/握手、golden与scoreboard设计门级仿真，只接入冻结DC网表/单元模型及SAIF窗口采集。若源数据不足98304对或数值/协议未经验证，先补测试侧证据，不由功耗侧隐式重复或随机补齐。

未来每个 run 把实际 selector 和统计保存到 inputs/windows 中，不在此保留可变“当前数据集”。当前没有真实负载清单、payload 或通过回执。
