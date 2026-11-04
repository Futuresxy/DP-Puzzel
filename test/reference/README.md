# 数学参考

独立表达 spec 的数学目标，用于评价误差。硬件有限位宽、截断和周期行为由 `src/cmodel/` 表达，不能把数学参考与 CModel 混为一套判据。当前无实现。

当前 [exact.py](exact.py) 使用 Fraction 独立解码外部格式、计算精确数学参考及有限网格RTZ参考，并提供 TF32 FP64近似。它不导入 C++内部布局/算法或expected golden。
