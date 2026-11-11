# 数学参考

独立表达 spec 的数学目标，用于评价误差。硬件有限位宽、截断和周期行为由 `src/cmodel/` 表达，不能把数学参考与 CModel 混为一套判据。

当前 [exact.py](exact.py) 使用 Fraction 独立解码外部格式、计算精确数学参考及有限网格RTZ参考，并提供 TF32 FP64近似。它不导入 C++内部布局/算法或expected golden。

[logical.py](logical.py) 复用独立格式解码和 Fraction 原语，为 E96/E128、Q64 逻辑向量计算精确 dot+C，并只在最后做一次 FP32 RNE。维度显式使用 `logical_k`，不伪造硬件 `K_FP16`；每个 Q8/E16 group 使用已经展开的 scale。HiF4 的 e1/e2 分别作用于每4/8个元素，NVFP4 scale 按无符号 E4M3 幅值处理。该入口没有有限窗口截断、流水或 CModel 调用，不能作为尚未实现混合顶层的逐位 RTL golden。

逻辑数据 golden 同时保存精确有理数（十进制字符串分子/分母）、数值分类、零/无穷符号和 invalid 状态；FP32 输出单独保存。上游 FP64 结果只是交叉检查来源，8笔二次舍入差异和独立相邻 FP32 距离检查见 [导入报告](../results/mixed-dp-data-20261107.md)。
