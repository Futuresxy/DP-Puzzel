# 真实负载选择与 RTL 测试数据

canonical 输入、独立 golden、scale/C 策略和事务时序归 `hw/test/vectors/` 与其回归流程维护。这里保存选择规则或小型 selector，不复制 tensor、向量和 golden；大型 payload 继续由 RTL 测试清单引用的归档提供。

正式 selector 需要 dataset manifest/path/hash、export/verification ID、格式/模式、真实片段或 task ID、顺序区间和边界定义，字段见 [输入契约](../input-contract.md)。它必须证明所选数据确实被相应 RTL 验证覆盖，不能只取文件名近似的数据。

保留握手、气泡、stall、K 分块累加和原始权重复用。新增片段先在测试侧版本化并回归；数据不足时不能由功耗侧随机补齐。源测试未包含真实调度时，保持 continuous-compute 标签，不能伪造 task trace。

DP 默认 selector 请求131072个有效标量MAC。H16/Q32/E64每次完整有效PE输入调用处理16/32/64个标量对，分别需要8192/4096/2048次调用；实际量按验证元数据的active lane/packing核验。固定MAC时调用数不同，不能按相同调用数投喂不等计算量。每调用K_call与任务总K_job分开保存，准备调用与计数burst分开，源序列/累加依赖完整；不足整笔时必须有已验证的合法partial-dot协议，不能静默取整或把padding算有效MAC。

未来每个 run 把实际 selector 和统计保存到 inputs/windows 中，不在此保留可变“当前数据集”。当前没有真实负载清单、payload 或通过回执。
