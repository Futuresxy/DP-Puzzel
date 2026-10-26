# PE_Q：单文件32路FP8/FP6计算

对应源码：[PE_Q.scala](../../../chisel_src/pe/PE_Q/PE_Q.scala)。本文件完整展开输入寄存、四格式转换、乘法、全K对齐和累加，取消DataUnpack_Q、SubPE_Q、PEGroup_Q与Utils整条规约Module。`PE_Q_g4`保留原16word/4scale槽布局及RTL名，g4不表示PG实例。

## 格式转换与scale

每W16 word有两个byte lane，FP6只读取每byte低六位。四种格式独立解包为E5/bias15与4位UQ1.3尾数，4位含hidden；A/B可在四种Q格式间合法混合。直接逐lane连接，不再为跨模块接口进行nibble2打包。

| 元素格式 | 正规数指数 | 4位有效尾数 |
| --- | --- | --- |
| E5M2 | 原指数 | hidden/m2/0 |
| E4M3 | exp+8 | hidden/m3 |
| E3M2 | exp+12 | hidden/m2/0 |
| E2M3 | exp+14 | hidden/m3 |

非正规数使用hidden=0、指数1+bias差。E5M2的全1指数分类NaN/Inf；E4M3只有全1幅值是NaN，其最高指数的其余码仍有限；FP6所有指数码有限。special用独立sideband，数值占位不作为特值解释依据。

每操作数32元素共享slot0的E8M0 scale。0xff为NaN，其数值指数占位127；其余scale使用原8位指数。S01/S02流水公共`scaleA+scaleB−254`，S03在MAX后加到top_anchor，不改变lane deltas。E8M0没有尾数乘法，其他scale槽不参与此路径。

## 流水与精度边界

| 级 | 本文件直接可见的逻辑 |
| --- | --- |
| S01 | 保持原compact边界，寄存packed输入、格式及scale状态 |
| S02 | S01之后组合解包；32个4×4产品自然W8/UQ2.6，top_anchor=expA+expB−29 |
| S03 | 全32路MAX，统一附加block scale指数，零不参与非零MAX |
| S04 | 饱和指数差 |
| S05 | 幅值逻辑右移后施符号的RTZ对齐 |
| S06–S08 | 每拍一级pair +&自然增长 |
| S09 | 剩余四项用两层组合平衡树规约，自然和W=A+5 |
| S10–S11 | 通用PENormalizeExact无损规格化自然和，最终显式RTZ掉3个低位 |

最终输出W=A+2/F=A；q_align_width/group_guard_bits不作用于此专用路径。没有字内或PG局部对齐/求和，不能把共享QE/HQE的误差合同套用到此路径。

## 接口、输出坐标与复位

`in_cfg`是整个batch保持稳定的配置电平，`in_data`和`out_data`均为Valid-only，无ready/反压。有效非法格式触发assert。基础PE以cfg的A/B数据类型和scale类型为权威；payload内重复字段不控制计算。输入尾部由上游补零。

输出为`{magnitude, negative, top_anchor, is_zero, special}`，公共`F=pe_align_width`，总载体`W=F+2`，magnitude为`W-1`位、anchor为signed W11：

`value = (-1)^negative * magnitude * 2^(top_anchor-F)`。

输入到输出经过11个寄存边界，S11输出，II=1。所有valid同步复位为0；数据寄存器不复位，仅在有效事务时更新。气泡沿valid逐拍传播，复位丢弃在途事务。anchor、special与数值在同一事务的各级同时推进。接入K/MN时仍在S11与C会合，总18级。

## 验证边界

本次重构检查见[记录](../../pe-code-locality-checks.md)。新旧导出抽样逐拍一致与固定延迟检查不等于独立全格式精度验收；完整边界/误差/负载质量回归、DC时序与功耗仍待完成。
