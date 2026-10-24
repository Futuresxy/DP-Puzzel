# H16/Q32全局对齐与流水自然和

对应源码：[PEGlobalAlignNormalize.scala](../../chisel_src/Utils/PEGlobalAlignNormalize.scala)。

H/Q专用组织，保留四个产品PG簇；共16/32个产品只经过一次全局对齐。S03平衡MAX并保持首lane平局规则；S04指数差饱和；S05每lane独立magnitude右移再施符号，实现RTZ，避免大N输入重排交叉网络。窗口A=pe_align_width，零anchor屏蔽。Q的公共E8M0 scale指数在MAX之后统一附加，不影响lane deltas。

S06/S07/S08各一层pair +&，S09收尾H两项/Q四项，所有乘加自然增长；和宽H=A+4、Q=A+5。S10/S11用PENormalizeExact无损规范化自然和。然后H丢最低2bit、Q丢最低3bit magnitude（RTZ），保持anchor，以得到统一W=A+2/F=A的PE结果。这是明确的最终精度边界。

同一输出layout/保留位数不意味着与HQE/QE分级RTZ bit-exact，后者在字内/PG层先丢位；公平比较需固定输入/频率/工艺、输出协议和质量验收，并分别报告数值误差。q_align_width/group_guard_bits不作用于此全局通路，不给专用路径增加被删除的局部对齐器。

从PE输入S00到S11、II1、无反压；各stage valid复位0，payload RegEnable。当前只做定向单位值坐标/valid检查，完整浮点/scale/误差回归与PPA待后续完成。
