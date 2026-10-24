# FormatCompat.scala：合法模式与特殊值

对应源码：[FormatCompat.scala](../../chisel_src/config/FormatCompat.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

硬件组合函数集中判断 A/B 和 data/scale 兼容性，避免不同层各自接受不一致组合。H 只允许同类型 FP16×FP16/BF16×BF16；Q 的四个 FP8/FP6 编码可两侧独立混合；E2M1 与 NVFP4 可混合；HiF4 只同类型。H 的 scale NONE/E8M0 均合法但数据通路使用虚拟 unit scale；MXFP8/6/4 要求 E8M0，NV 要求 E4M3，HiF4 要求源 E6M2。

canonical product：Q 统一 E5M2 carrier；E2M1/NV 任一侧是 NV 则用 NV 固定点坐标，否则 E2M1；H/HiF4 保留。不能把 canonical 类型用于重新解码另一侧原始数据。

`SpecialValueFlags` 包含 is_nan/is_pos_inf/is_neg_inf，组合 mergeAdd 合并任意非空输入集：NaN 或异号 Inf 同时出现均产生 canonical NaN，否则保留单符号 Inf。laneMask 只启用 packed word 的 1/2/4 个 lane。位宽由调用者提供且必须为正，返回 mask 同宽。

无寄存器/延迟/复位，电路在调用 Module 中展开。非法请求在 PETile cfg 握手与 MidGroup/DataUnpack 输入断言处检查。待 SV 验证全部编码组合、混合格式 canonical、0×Inf、scale 特殊值、异号 Inf 合并及无效周期屏蔽。
