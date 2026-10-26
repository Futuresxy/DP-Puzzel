# PE_E：保留分级算术，PE级计算直接可读

对应源码：[PE_E.scala](../../../chisel_src/pe/PE_E/PE_E.scala)。合法profile为PE_E_g4和PE_E_g2。按用户确认保留DataUnpack_E、SubPE_E、PEGroup_E模块及其局部数值语义；从Utils移回PE输入分发、跨PG MAX/对齐/求和、valid流水和最终输出连接。没有PEWiring或PEAlignNormalize包装。

## 读代码的顺序

1. S00检查cfg支持能力、A/B组合及各自data/scale组合；逐PG切分四个W16 word和HiF4 g0/g1。
2. A/B独立选择scale槽：MXFP8/6及HiF4为slot0，MXFP4为0/0/1/1，NVFP4为0/1/2/3；g2使用前两组映射。
3. 实例化PEGroup_E并直接读取S06 anchor与S07数据。局部乘法器复用、字内/PG RTZ与scale-tail乘法仍在原PG/SubPE文件。
4. S07对PG anchor做平衡MAX；全部零使用安全基准0，零哨兵−1024不能赢过非零项。寄存winning index和全部anchor，与PG的S07数据会合。
5. S08直接计算饱和指数差、精确低零placement，以及MAX旁路和g−1个RTZ移位器的通用连接。负数floor修正计数与数值一并寄存；special在同级合并。
6. S09通过通用CSA把修正计数并入精确和，完整保留ceil(log2(g))个进位位。
7. S10/S11实例化通用PENormalizeExact完成abs/LZD、规格化和anchor修正，明确连接所有公共输出字段。

## 位宽与坐标

E的PG输出W=20+group_guard_bits，默认22；MX/NV的I=13、HiF4的I=11，raw到top偏移分别为12/10。 这些模式偏移表直接写在PE文件，不需要跳转到Utils寻找PE专属坐标转换。

令A=pe_align_width、g为实际PG数。placement只补低零、不窄化PG输入；signed自然和W=A+ceil(log2(g))，raw top anchor也加同样的carryBits。g4的自然和W=A+2，规格化后直接输出；E_g2自然和W=A+1/F=A−1，S11规格化幅值低端精确补一个0到F=A，normalized anchor和符号保持不变，并assert有效输出LSB=0。

PG间移位仍是有损RTZ；最终规格化与g2补零无损，不能恢复局部已丢失的位。与H/Q全K单次对齐需分别记录误差。

## 接口、输出坐标与复位

`in_cfg`是整个batch保持稳定的配置电平，`in_data`和`out_data`均为Valid-only，无ready/反压。有效非法格式触发assert。基础PE以cfg的A/B数据类型和scale类型为权威；payload内重复字段不控制计算。输入尾部由上游补零。

输出为`{magnitude, negative, top_anchor, is_zero, special}`，公共`F=pe_align_width`，总载体`W=F+2`，magnitude为`W-1`位、anchor为signed W11：

`value = (-1)^negative * magnitude * 2^(top_anchor-F)`。

输入到输出经过11个寄存边界，S11输出，II=1。所有valid同步复位为0；数据寄存器不复位，仅在有效事务时更新。气泡沿valid逐拍传播，复位丢弃在途事务。anchor、special与数值在同一事务的各级同时推进。接入K/MN时仍在S11与C会合，总18级。

## 验证边界

本次[重构检查](../../pe-code-locality-checks.md)仅证明所采样输入的新旧RTL输出/控制一致，并独立检查11级valid；既有单位值smoke也不等于完整浮点精度验收。独立全格式/scale/误差回归及DC/功耗尚未完成。
