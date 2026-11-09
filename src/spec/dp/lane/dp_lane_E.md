> 功能：定义E8专用lane窄规约与S3局部e2融合；范围：混合DP专用前端及扩展合同；版本：v1.9；修改时间：2026-11-09 22:25:29 +0800；对应代码：src/verilog/lane/dp_lane_e.v、src/verilog/unpack/dp_lane_unpack_e.v、src/cmodel/lib/lane/lane_e.cpp；本版待实现，现有源码与旧PPA不代表本合同已验收。

# E8 专用 lane

v1.8 → v1.9：~~S4组合融合e2、S3保存S12及e2~~ → S3完成e2融合并保存S14，e2不传出lane。适用于三种混合顶层的E扩展迁移；独立E64现有实现不得静默改变或继承新验收。

## 1. 能力与专用解包

每lane每拍8项，支持MXFP4/NVFP4/HiF4；不支持T/H/Q/INT8。独立组合 `dp_lane_unpack_e` 每侧处理32位原始数据，输出8×U4幅值及8位符号，S1由lane寄存。删除高精度指数、分类与模式选择逻辑；保留负零符号、HiF4 e1/e2及group的scale特殊语义。

MX/NV幅值coefficient为{0,1,2,3,4,6,8,12}，I3F1；HiF4为(raw&7)<<e1，I2F2。e1按原布局融合到幅值，不能跨e1粒度错误合并。HiF4 p=e2_a+e2_b，为U2、范围0..2，每lane共享。MX/NV固定低补2零；无跨lane MAX/delta或宽右移器。scale广播仍按[layout](../dptop/layout-and-scales.md)。

## 2. 流水与位宽

S/U后的数字为总位宽；SIF中的I不含符号位。

|阶段|计算|寄存数据主体|
|---|---|---|
|S1|专用解包、e1融合|两侧8×U4及符号/局部控制|
|S2|8个U4×U4→U8，符号化S9，两两相加|4×S10 pair|
|S3|四项平衡树S10→S11→S12；先符号扩展S14，再左移p；MX/NV固定补2零|S14 lane结果；不再寄存/输出e2|
|S4|由group接收两个S14并求和/abs|group持有U14＋sign|
|S5|group scale/LZD/token|见[group合同](../group/dp_group_E.md)|

|信号/精度|S|I|F|
|---|---:|---:|---:|
|MX/NV乘积幅值|0|6|2|
|HiF4乘积幅值|0|4|4|
|MX/NV pair|1|7|2|
|HiF4 pair|1|5|4|
|MX/NV原始lane和|1|9|2|
|HiF4原始lane和|1|7|4|
|S3全部E融合后|1|9|4|

HiF4 lane绝对值≤8×14²×4=6272，MX/NV≤8×12²×4=4608，S14足够。必须先扩位再左移，无截断或中间舍入。每lane保留8个乘法能力，不允许用4个乘法器分两拍冒充II=1。

## 3. 控制与验收

valid每拍推进，payload由本级valid及参与位使能，同步低有效rst_n。保留原始乘积符号的all_negative，不能从pair/lane和符号推导负零。S3融合后e2不传给group；控制必须属于在途请求。

不在本轮增加独立e1乘法重构或S2整树融合。先CModel更新切点，再RTL回归，覆盖元素编码、全部e1/e2组合、两个lane不同e2、抵消、负零、连续换型/气泡/复位。S2乘法+pair及S3树+小移位的1GHz时序须新DC验证；寄存位减少不等于已测面积收益。
