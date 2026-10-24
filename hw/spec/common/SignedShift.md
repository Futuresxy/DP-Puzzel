# SignedShift.scala：显式 signed RTZ 移位

对应源码：[SignedShift.scala](../../chisel_src/common/SignedShift.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

核心合同：RTZ(x,d) = (x >>> d) + [x<0 且丢弃位非零]。rightTowardZeroParts 返回 floor 和 correction；rightTowardZeroToWidth 执行校正并显式裁剪/扩展到目标宽度。每级 barrel 同时收集 discarded sticky，避免用双 abs 网络。

宽度 W>0、shift 宽度>0，超窗口移位使负数 floor=-1/correction=1，结果为 0，也正确覆盖最小负数。rightTowardZeroLimited 额外在 d>maxShift 时输出0，maxShift≥0。缩窄目标时调用者必须证明高位可丢，helper 不替调用者证明数值无损。

纯组合内联，无时钟/复位/valid，使用在 SubPE、PG 和 MidGroup 有效流水内。待 SV 以正负极值、d=0/W−1/W/超过W、discarded=0/非0 和非二次幂 W 验证，尤其不能误把算术右移直接当 RTZ。
