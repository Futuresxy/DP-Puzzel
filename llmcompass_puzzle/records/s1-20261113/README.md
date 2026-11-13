# S1：面积接入与原始 A100 CPU 重放（2026-11-13）

本批次是独立新主线的接口验证，未运行 DeepSeek 推理 DSE；全部性能数字来自上游原始标量阵列/算子，不是新 DP 阵列测量。详细来源、输入/源码/输出 hash 见两个 manifest 与 [evidence.json](evidence.json)。

## 运行与验证

```bash
bash llmcompass_puzzle/run_reference.sh llmcompass_puzzle/runs/s1-reference-20261113-v3
llmcompass_puzzle/.venv/bin/python -W ignore::ResourceWarning -m unittest discover -s llmcompass_puzzle/tests -v
```

运行目录已保留且不覆盖，复现时换用新的目录名。四项集成测试通过：工艺代理不虚构泄漏/时序、面积替换守恒与物理/启用核心分离、vector 吞吐与 ALU/RF 成本耦合、真实 SCALE-Sim/GEMM/Softmax CPU 重放。测试仅忽略已知上游 ResourceWarning，不忽略数值失败。

## 面积与峰值账本

参考模型面积 **826.763555 mm²**，是上游模型预测值，不是实测芯片面积。物理 128 SM、启用 108 SM、每 SM 4 个 4×4 DP、共同 1 GHz；九配比 BF16 峰值均为 **221.184 TFLOP/s**。N12 采用 DeepScaleTool 14→7nm 代理，增量阵列外围面积暂设为零。

| H:Q:E | 原档 vector 下总面积 mm² | 满足参考面积预算 |
|---|---:|---|
| 1:2:4 | 810.476144 | 是 |
| 1:2:6 | 813.515226 | 是 |
| 1:2:8 | 816.593713 | 是 |
| 1:4:4 | 819.318348 | 是 |
| 1:4:8 | 822.895390 | 是 |
| 1:2:12 | 822.252089 | 是 |
| 1:2:16 | 825.713159 | 是 |
| 1:6:12 | 835.333985 | 否 |
| 1:8:16 | 845.123390 | 否 |

在这个固定核心数情景中，vector 0.5×/1×/2× 的面积可行点分别是 **9/7/0** 个。这只表明资源机会成本：后续要重配核心、vector 或存储，不能由本表推断推理排名。面积比例和最优设计仍受工艺代理、外围成本、RF端口模型与存储配置影响。

## 原始 A100 重放

原始性能对象维持 1.41 GHz、108 SM、2.039 TB/s HBM、5120 B/cycle L2。16×16×16 标量 OS 案例为 45 周期；另外两项 GEMM 运行上游 heuristic-GPU CPU mapper；两项 Softmax 运行上游 vector 模型。见 [GEMM CSV](a100_gemm_replay.csv) 和 [Softmax CSV](a100_vector_replay.csv)。秒数不含完整 launch/通信或模型图，也不能与 1 GHz DP 峰值表构成实测加速比。

## 下一阶段与校准边界

S2 接入 native-K、L8/II1、尾部、累加反馈和不同格式真实字节；S3 接 DeepSeek prefill 图及合法 Norm 融合量化增量、非 GEMM 和通信；S4 才运行四个成对研究问题。主图见 [实验协议](../../EXPERIMENTS.md)。

校准先在同 SKU/时钟下对持出 GEMM/Softmax 的独立设备 trace 或可信公开 kernel 数据比较，分开 launch、缓存状态与映射误差；新 DP 阵列时序/供数、N7 工艺和整芯片功率需分别表征，不能继承上游验证精度。当前未进行 GPU 测量，也不宣称满足 A100 400W 整卡功率约束。
