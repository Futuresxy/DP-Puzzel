# PE_H：单文件16路高精度计算

对应源码：[PE_H.scala](../../../chisel_src/pe/PE_H/PE_H.scala)。本文件直接实现FP16/BF16解包、乘法、全K对齐和累加，取消DataUnpack_H、SubPE_H、PEGroup_H与Utils整条规约Module。`PE_H_g4`保留原输入布局和RTL名，g4不表示四个PG实例。

## 数值与资源组织

16个W16输入word各包含一个H元素。FP16解包为hidden+10fraction，BF16为hidden+7fraction再补三个低零，均嵌入UQ1.10。非正规数hidden=0、biased exponent=1；NaN/Inf使用零数值占位及独立special分类，0×Inf为NaN、相反符号Inf相加为NaN。

S02有16个独立11×11乘法器，产品自然W22/UQ2.20。每个产品的`top_anchor=expA+expB-2*bias+1`，表示物理magnitude bit21的指数；FP16 bias15，BF16 bias127。零产品anchor使用−1024哨兵，不能参与非零MAX。H使用虚拟unit scale，既不解码输入scale数值，也不产生scale乘法器；允许NONE/E8M0类型。

## 流水与精度边界

| 级 | 本文件直接可见的逻辑 |
| --- | --- |
| S01 | 格式解包、特殊值分类，寄存UQ1.10尾数/指数/符号及格式 |
| S02 | 16路W22乘积、符号、零标志、anchor |
| S03 | 全16路平衡MAX，寄存所有产品及最大anchor |
| S04 | 每lane指数差，饱和到A=pe_align_width |
| S05 | 精确补低零放入窗口，再对幅值逻辑右移、最后施符号，实现RTZ |
| S06–S08 | 每拍一级pair加法，使用+&自然增长 |
| S09 | 剩余两项相加，全局和自然W=A+4 |
| S10–S11 | 实例化通用PENormalizeExact完成abs/LZD及无损规格化；最终显式RTZ掉2个低位 |

最终RTZ得到公共W=A+2/F=A输出，保持normalized anchor。此实现只有一次全K动态对齐；q_align_width与group_guard_bits不作用于H路径。相同公共输出窗不意味着与HQE分级RTZ有相同误差。

## 接口、输出坐标与复位

`in_cfg`是整个batch保持稳定的配置电平，`in_data`和`out_data`均为Valid-only，无ready/反压。有效非法格式触发assert。基础PE以cfg的A/B数据类型和scale类型为权威；payload内重复字段不控制计算。输入尾部由上游补零。

输出为`{magnitude, negative, top_anchor, is_zero, special}`，公共`F=pe_align_width`，总载体`W=F+2`，magnitude为`W-1`位、anchor为signed W11：

`value = (-1)^negative * magnitude * 2^(top_anchor-F)`。

输入到输出经过11个寄存边界，S11输出，II=1。所有valid同步复位为0；数据寄存器不复位，仅在有效事务时更新。气泡沿valid逐拍传播，复位丢弃在途事务。anchor、special与数值在同一事务的各级同时推进。接入K/MN时仍在S11与C会合，总18级。

## 验证边界

本次重构检查见[记录](../../pe-code-locality-checks.md)。新旧导出抽样逐拍一致与固定延迟检查不等于独立全格式精度验收；完整边界/误差/负载质量回归、DC时序与功耗仍待完成。
