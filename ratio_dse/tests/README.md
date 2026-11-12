# 模型回归

从仓库根运行。

```bash
python3.11 -m unittest discover -s ratio_dse/tests -v
bash ratio_dse/run_examples.sh
```

回归覆盖锁定证据、九配比峰值、整数面积边界、广播和块 scale、独立手算 dense/grouped/ragged/expert 形状与反馈时序、V4/V4.1 工作量重放、短 decode、路由观测与固定部署精度迁移。样例运行覆盖两种面积场景、两代 DeepSeek 账本和可计算完整本地时间的合成 GEMM。

DSE 回归另以手算例核验跨核 tile 分派、同核端口分配、专家池化、DP 功耗上限和 Pareto 并列。完整扫参运行输出逐场景不变量检查。硬件校准计划见 [DSE 报告](../results/summaries/deepseek-dse-20261113/README.md#expand-and-validate)。
