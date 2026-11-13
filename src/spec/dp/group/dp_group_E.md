> 功能：定义E16组、LZD22与公共S5双指数接口；范围：混合DP专用前端及扩展合同；版本：v1.9.1；修改时间：2026-11-10 00:16:17 +0800；对应代码：src/verilog/group/dp_group_e.v、src/cmodel/lib/group/group_e.cpp；本版CModel与冻结RTL已通过，见test/results/mixed-rtl-v1.9.md；PPA按独立回执验收。

# E16 专用 group

包含两个[E8 lane](../lane/dp_lane_E.md)。v1.8 → v1.9：~~旧anchor/z后端接口~~ → A_raw/compare_exp双指数接口，显式LZD22；S4不再处理e2。

## 1. S1–S5

S1专用scale解包输出无偏S8指数，NV/HiF系数U4；S2指数S8+S8→S9、系数U4×U4→U8。不得再减254。S3预计算A_raw并同步延迟；S4两个S14 lane结果相加为S15，取U14幅值与独立sign；S5做NV/HiF U14×U8→U22或MX旁路、LZD22、compare_exp并寄存。

定义alpha_scale为两侧解码后的无偏指数和。组和Q_group表示Q_group×2^-4。S4格式为S1I10F4，幅值≤12544，因此安全取14位abs。S5 NV/HiF系数为U8 I2F6，乘积U22 I12F10。

## 2. U22内部容器、U31外部接口

令M=LOCAL_W+3（默认31，要求M≥22）：

```text
NV/HiF：m22 = group_mag14 * scale_coeff8
MXFP4： m22 = {group_mag14, 8'b0}
m_out = {m22, (M-22)个0}
z22 = LZD22(m22)
```

|模式|m22格式|最终M位幅值格式|A_raw（非零有限）|
|---|---|---|---|
|MXFP4|I10F12|I10F(M-10)|alpha_scale+9|
|NVFP4/HiF4|I12F10|I12F(M-12)|alpha_scale+11|

A_raw始终对应最终M位幅值最高物理位，不改为22位坐标。对非零m22，LZD_M(m22<<(M-22))=LZD22(m22)，不加M-22、不改A_raw。故compare_exp=A_raw-z22。

全零LZD22通常返回22，而M位LZD返回M；零不得参加MAX。只有请求参与、有效、幅值非零、无特殊分类时compare_exp有效，否则置0占位并用active屏蔽。若保留out_z作观察，零幅值可返回M，有限非零返回z22；特殊源的观察值不作数值合同，不以A_raw-compare_exp重建零的真实LZD。

|S5字段|默认宽度|定义|
|---|---|---|
|magnitude|U31|未归一化，MX低补17零；NV/HiF低补9零|
|negative|1|独立符号，含零符号规则|
|anchor|S10|A_raw|
|compare_exp|S10|A_raw-z22，供MAX|
|special/valid|既有宽度|保留scale特殊分类、请求拍对齐|

LZD输入使用MUX后的统一U22；不要对MX原始U14直接取z后配套错误的A_raw。低补零为连线；DC可能已优化旧LZD常量输入，因此不预报节省面积。

## 3. 参与、兼容与验收

group仍S5输出，II=1。顶层不参与掩码、特殊值及负零归约按[混合合同](../dptop/mixed-precision-expansion.md)。不得删除scale零/特殊编码处理。输入scale广播按逻辑量化块，非每个E16独立量化。

先验证U22/M位LZD对全部非零位位置及零的区别、MX旁路补8零、NV/HiF最大乘积、严重抵消、负零、无偏scale边界；再验证S5实数不变量和S6后端。旧E64/PPA仅为历史，独立E64迁移需另有范围与新回执。
