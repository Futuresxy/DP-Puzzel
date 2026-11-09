> 功能：定义Q8E16专用组双指数迁移；范围：混合DP专用前端及扩展合同；版本：v1.9；修改时间：2026-11-09 22:25:29 +0800；对应代码：src/verilog/group/dp_group_qe.v、src/cmodel/lib/group/group_qe.cpp；本版待实现，现有源码与旧PPA不代表本合同已验收。

# Q8E16 专用 group

两个[Q4E8 lane](../lane/dp_lane_qe.md)，只支持Q/E。v1.8 → v1.9：~~旧scale偏置/z接口~~ → 无偏scale、S3 A_raw、S5 compare_exp，与基础dp_top v1.8一致。

## 1. 计算与位宽

S1 scale解包S8无偏指数和U4系数；S2指数和S9、系数积U8。元素公共MAX仅Q参与；E固定坐标，HiF4 e2在lane内消耗。S3按模式计算A_raw，S4延迟至S5。

S4两个lane分别输出S31（LOCAL_W+3）；S5两项相加为S32，取U31幅值；NV/HiF提取结构性低零之上的U14，乘U8得到U22，再低补9零；Q/MX旁路。各格式布局、group_fraction和A_raw必须与基础v1.8一致，不能保留旧HiF4指数坐标。

S5保留共享LZD31，因为Q可能使用完整U31位宽；不另复制E专用LZD22。保存magnitude U31、sign、A_raw S10、compare_exp S10和special/valid。compare_exp=A_raw-z，仅有限非零源有效；零/特殊源不得以占位0参与MAX。

## 2. 控制及验证

扩展QE不支持INT8/T/H，静态裁掉这些模式的解包/运算/选择；保留所有Q/E特殊语义和scale处理。Q元素指数与E旁路按级门控，组token按有效请求捕获。默认28/40，合法参数的位宽和补零由公式推导。

S5比E专用group多串联组和/abs，必须单独检查时序，不能用E前端时序代替。先CModel更新，再对照基础v1.8 Q/E算术与S5 token；在混合顶层验证参与屏蔽、全负指数、负零及特殊冲突。顶层规则见[混合合同](../dptop/mixed-precision-expansion.md)。
