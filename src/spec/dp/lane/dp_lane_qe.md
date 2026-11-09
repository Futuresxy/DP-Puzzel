> 功能：定义Q4E8专用lane裁剪和E旁路；范围：混合DP专用前端及扩展合同；版本：v1.9；修改时间：2026-11-09 22:25:29 +0800；对应代码：src/verilog/lane/dp_lane_qe.v、src/verilog/lane/dp_lane_align.v、src/verilog/lane/dp_mantissa_bank.v；本版待实现，现有源码与旧PPA不代表本合同已验收。

# Q4E8 专用 lane

支持MXFP8 E4M3/E5M2、MXFP6 E3M2/E2M3、MXFP4/NVFP4/HiF4；不支持T/H/INT8。v1.8 → v1.9：~~E参与旧局部指数对齐~~ → E窄pair旁路宽移位与跨lane MAX，S4共享树末端融合局部e2。用户指定S3融合e2针对E专用lane；QE树仍在S4，其e2在本lane S4消耗，不传到group。

## 1. 专用解包和乘法

沿用已优化的QE固定字段紧凑解包及分类压缩，不重新引入通用高精度Number展开。Q保留规范要求的指数映射、隐含位、非正规/特殊分类；E保留e1解码和符号。删除T/H的8位元素指数加法、宽尾数拼接和INT8选择。

乘法能力为E每拍8个U4×U4；Q每拍4个U4×U4，复用其中四个，不为Q额外复制整组。Q指数U5+U5→U6，MAX/delta使用足够宽度；HiF4 e2为U1+U1→U2。group的scale指数仍S8+S8→S9，不能与元素指数混淆。

## 2. 流水与门控

|阶段|Q模式|E模式|
|---|---|---|
|S1|紧凑Q解包/分类|E解包、e1及e2旁带|
|S2|乘法、U6指数和、lane及跨lane MAX|乘法，MAX候选active=0|
|S3|delta、U28幅值RTZ、符号恢复S29|S10 pair、静态落位到S29；绕过宽右移|
|S4|四项共享树S29→S31|共享树后融合局部e2，输出同坐标S31|
|S5|group求和/scale/token|group求和/scale/token|

LOCAL_W参数化；LEAF_W=LOCAL_W+1，LANE_SOP_W=LEAF_W+2。E按基础dp_top v1.8的定点布局适配，不用旧HiF4跨lane指数差。共享树、E恒零低位及精度分段寄存使能沿用基线思想；Q指数、MAX/delta、宽移位输入在E模式下隔离。寄存使能使用源级精度，读取使用目标级精度，支持逐拍换型。

## 3. 数值与实施边界

Q对齐叶子为S1I2F(LOCAL_W-2)，lane和S1I4F(LOCAL_W-2)。E自然S10 pair、S14融合结果的数值定义复用[E lane](dp_lane_E.md)，但QE在共享容器中计算，必须显式保留增长/补零且group输出与基线v1.8同坐标。

本轮不复制独立E树、不把Q移位删除、不缩小LOCAL_W、不将e2提前作用到未完成的异构pair。保留Q特殊值/all_negative；不能仅减少输出字段而改变异常或负零。

验收Q四格式、E三格式、零/非正规/特殊输入、局部不同指数/e2、抵消、混精度换型、门控保持及复位；S3/S4断点分别对照模型。旧QE面积优化记录见Git历史及hw/dc_syn/records，不能归为本版收益。
