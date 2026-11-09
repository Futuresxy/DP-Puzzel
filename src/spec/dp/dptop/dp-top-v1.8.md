> 功能：dp_top v1.8 实施合同；范围：基础 T8H16Q32E64，K4/8/16、LOCAL_W/GLOBAL_W 合法变体；版本：v1.8；修改时间：2026-11-09 17:59:28 +0800；对应代码：[dp_top.v](../../../verilog/top/dp_top.v)、[CModel](../../../cmodel/lib/model.cpp)；状态：已批准合同，CModel/RTL 已实现并通过本批功能验证。

# dp_top v1.8 实施合同

本批先实现并验证 dp_top；其他 E/QE/混合顶层维持 v1.7，实现不得因共用模块语义改变而静默迁移。共用模块使用静态能力参数保留原合同，只有 dp_top 显式启用新路径；参数不是运行时功能输入。冻结 SV 不变。

## 1. 流水与数值

保持 L8/II=1、同步低有效 rst_n、每拍可换型、无输出背压。默认 K16/28/40。S/I/F 中 I 不含符号；所有结构补零精确，不新增舍入。

| 级 | 操作与寄存 |
| --- | --- |
| S1 | A/B 紧凑解包保持；scale 幅值 I1F3、指数改为 signed8 无偏值；C 只延迟原编码 |
| S2 | 共享元素乘法；T/H/Q 公共 group MAX；E 不参与 MAX。HiF4 保存 p=e2a+e2b；scale 4×4 系数积和 signed9 指数和 |
| S3 | T/H/Q 对齐后符号化；INT8 静态落位旁路；E 四个 signed10 pair 旁路宽移位。group 并行预计算 A_raw |
| S4 | lane 共享四叶树；HiF4 lane 和扩位后左移 p，MX/NV 静态补两零，统一 F4；A_raw 同拍传递 |
| S5 | 两 lane 组和、abs、NV/HiF 14×8 scale、LZD；计算 compare_exp=A_raw-z。C 解包但不检测前导零 |
| S6 | 按 compare_exp 求带 active 的 MAX；原幅值一次双向移位、符号恢复；保存有符号叶子及共同指数 |
| S7 | 四组 4:2 压缩、两行与 C 做 3:2 压缩、一次最终 CPA；K4/8 将未用组补零 |
| S8 | 总和 abs/LZD、FP32 RNE/特殊选择或 INT32 回绕，输出寄存 |

## 2. E lane 固定坐标

q_i 为独立符号注入后的乘积 coefficient。S3 pair 为 signed10：MX/NV S1I7F2，HiF S1I5F4；共享树得到 signed12：MX/NV S1I9F2，HiF S1I7F4。

S4 MX/NV Q_lane_fixed=sum(q_i)<<2；HiF Q_lane_fixed=sign_extend_14(sum(q_i))<<p，p∈{0,1,2}。两者均 signed14/S1I9F4。先扩位后左移；嵌入公共 W_lane 容器时低补 W_lane-14 位。E 的四个 pair 不取 abs、不进宽移位、不恢复第二次符号。S3 pair 可按相同结构补零接入共享树，低零寄存器按精度隔离；不能丢失符号或改变数值。

group 合并为 signed15/S1I10F4，幅值14位。NV/HiF 乘 unsigned8/I2F6 得 unsigned22/I12F10；默认低补9零进入 M31，F19。MX 14位幅值低补17零，F21。HiF e2 已消耗，不得再加公共 r。

## 3. scale 与提前 anchor

单侧 scale 解包 E8M0: raw-127；E4M3: max(raw_e,1)-7；E6M2: raw_e-48；NONE:0。NaN 分类独立并使用安全指数占位；不改变幅值和零规则。signed8覆盖-127..127；S2 先符号扩展再相加到signed9。

S3 A_raw = r_effective + scale_exp_sum + (M_group-1-F_group-2*element_bias)。E 的 r_effective=0；无scale的指数和为0；INT浮点字段占位。括号为各模式常量选择，F_group包含S5 scale乘法与补零，不能再次扣254。S3计算原始候选，S5根据幅值/特殊值屏蔽；默认 M_group=31。

## 4. S5 token 与 C

组输出 magnitude/negative/anchor_raw/compare_exp/special/valid；compare_exp=A_raw-clz(magnitude)，无效源比较占位0。z仅内部观察，不必作为后端接口寄存。原幅值不动态规格化。

C 正规数 M32={1,fraction,8'b0}，A_raw=raw_exp-127；非正规 M32={0,fraction,8'b0}，A_raw=-126。compare_exp_c=A_raw_c，不做LZD、不清零非正规数。零/特殊值排除MAX，负零及特殊旁带保留。整数C不参与浮点MAX。

这是用户选择的数值合同改变：C 的 compare_exp 对非正规数是实际最高位指数上界，不保证真实 leading exponent。可能改变极小数和抵消时的窗口利用率及RTZ结果，不能宣称与v1.7全部bit-exact。数学golden保持独立精确；单独报告这类误差。

## 5. S6 单次移位与 S7 压缩

Emax=max(active compare_exp)。signed_shift_delta=Emax-A_raw；正值右移，负值左移。实现可保留等价 net=A_raw-Emax 端口，必须注明方向。幅值先低补零至GLOBAL_W-1；使用完整有符号差值，右移量过宽则0。INT静态旁路；S6完成补码恢复。C策略使最大源也可能最高位为0，不可假设存在规格化首位1。

S7 四个group先4:2压成两行，再与C做3:2，最后CPA。4:2可用两个3:2实现，不含中间CPA。carry统一定义为已左移的数值。输入先符号扩展到足够宽度；默认五个signed40输出signed43。固定宽度压缩遵守模2^W恒等式，最终精确总和必须落在signedW范围；不能把未对齐carry当普通加数。K4/8仅启用1/2组，最终宽度仍按GLOBAL_W+ceil(log2(G+1))。

## 6. 后续扩展分支（本批仅规格）

E32扩展=新增2个E16 group，扩展两项用ADD；E64或Q32E64扩展=新增4组，用4:2+ADD得到扩展部分和。这里是新增容量，不是独立E64顶层的重定义。

基础四组+C得到base_sum；扩展组得到extension_sum；selected_sum=extension_supported ? base_sum+extension_sum : base_sum。C只计入base_sum一次。base/extension必须在同一Emax和F下对齐后再求和，不允许各自Emax后直接相加。MAX、移位、特殊归约均在不支持精度时排除扩展支；对扩展寄存器及算术输入隔离。E扩展仅支持MX/NV/HiF；QE扩展支持MXFP8/6及三种E，不支持T/H/INT8。

扩展4:2后的ADD及最终合并ADD可能增加S7关键路径；扩展顶层保持L8的可行性待单独实现/综合，本批不承诺。所有新增group沿用A_raw/compare_exp token；不支持的支路不能用占位0指数压过负指数。

## 7. 验收

先CModel后RTL。等价项：E固定坐标、scale去偏置、anchor前移、CSA；例外项仅C非正规比较策略。覆盖各格式完整数据、HiF e1/e2与抵消、INT8 -128、C零/负零/最小与最大非正规/最小正规/特殊、连续混型/气泡/复位、K4/8/16及合法窗口。检查S3/S4/S5/S6/S7断点、S3提前anchor、S5 compare_exp及压缩恒等式。独立精确参考不可按硬件策略改写。

原PPA只代表旧快照；新RTL必须重新导出、验证。重点时序风险S4树后小移位、S5 LZD后减法、S7压缩与最终CPA。此批先功能验证，不凭功能PASS宣称1GHz或功耗收益。

v1.7→v1.8：~~E共享对齐、biased scale、S6计算A_raw-z、普通最终树、C LZD~~ → E局部融合、无偏scale、S3 anchor/S5 compare_exp、CSA、C保留0.xxx参与比较。

实施回执：[dp_top v1.8 验证报告](../../../../test/results/dp-top-v1.8.md)。当前已验证 L8/II=1 和数值/断点；未取得 v1.8 新 PPA。
