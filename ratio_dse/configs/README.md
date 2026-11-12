# 示例配置

- [area](area/) 含锁定的 N12 单 DP 证据清单、两种约束场景和三种 256 DP SM 拓扑。SM/AICore 基线数量与 TensorCore 面积占比均在场景 JSON 中设置。
- [compute](compute/) 含 V4/V4.1 prefill 场景、单阵列接口假设、精度方案和可独立导入的合成 GEMM。

复制相应 JSON 并显式修改实验参数。每次运行的 manifest 保留所用输入和文件 hash。字段说明见 [面积模型](../area_model/README.md) 与 [GEMM 模型](../compute_model/README.md)。
