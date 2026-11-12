# 工作负载职责

标准 GEMM 账本、外部模型输入与运行时观测字段见 [GEMM 模型](../compute_model/README.md#inputs)。现成示例位于 [configs/compute](../configs/compute/)。

单 GEMM、多 GEMM 集合、训练/推理阶段与端到端模型是不同评价范围，不能混称。大型张量和原始 trace 外部归档；配置、精简统计和引用元数据进入 Git。
