# MaxLaneAlign.scala：MAX 旁路和有限窗口对齐

对应源码：[MaxLaneAlign.scala](../../chisel_src/common/MaxLaneAlign.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

maximum 用平衡树返回有符号最大 anchor 及首 lane 获胜 index，支持单元素和非二次幂数量。index 至少 1 bit；相同 anchor 选择左侧即较早 lane。

apply 将 MAX lane 送 result0 旁路，其余 lane 重排进入 N−1 个 signed RTZ shifter。withCorrections 要求 N≥2：非 MAX 只生成 floor 和修正位，返回修正 PopCount 供 CSA 吸收。fromMagnitudes 在逻辑右移后施加独立符号，避免 abs 网络，实现同样 signed RTZ。

有符号输入全部同宽 W，magnitude 输入为 W−1，移位和 index 由调用者注册且必须与数据配对；返回 lane 顺序是 MAX 优先，适用于无序加法规约，不能当作原始 lane 顺序。零/特殊值 masking 在调用者，helper 不自行解释哨兵。没有独立 Module、寄存器、复位，delay 由调用者定义。

待 SV 检查 N=1/2/3/4/5、平局、负数、大移位及重排后求和不变；MAX bypass 不等于取消其他输入的必要对齐。
