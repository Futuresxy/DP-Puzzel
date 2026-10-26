# 集中参数、六种profile与配置读取

对应源码：[Parameters.scala](../../chisel_src/config/Parameters.scala)。

`Parameters` 是程序员修改默认参数的唯一入口；不可变 `AlignmentConfig` 显式沿顶层→PE→PG/SubPE/规约传递。没有隐式环境变量电路配置，CHISEL_FIRTOOL_PATH仅选择工具。

| JSON / CLI字段 | 默认 | 合法范围 | 生效路径 |
| --- | --- | --- | --- |
| q_align_width / --q-align-width | 28 | 26–30 | HQE/QE字内Q MIN对齐，signed product W9后保留窗口；Q专用全局路径不使用字内窗口 |
| group_guard_bits / --group-guard-bits | 2 | 2–4 | HQE/QE/E的PG局部对齐保护位；H/Q专用路径无PG局部对齐 |
| pe_align_width / --pe-align-width | 40 | 38–48 | 五族的PE对齐窗口；公共输出F及W=F+2 |
| top_align_width / --top-align-width | 40 | 38–48且≥pe_align_width | K/MN中的PE+C公共对齐窗口 |

require检查范围及PE窗口能容纳最大PG载体。乘法/加法没有自由位宽旋钮：产品宽为输入宽之和，有符号值加符号位，二叉和用+&增长，N项求和按ceil(log2(N))保留进位。窗口是有数值影响的精度参数，不能用控制移位量的bit数代替数据窗口宽。

配置优先级：Parameters默认 < JSON显式字段 < CLI覆盖。导出保存完整有效JSON、命令与source hash。修改默认不会覆盖JSON里明确填写的值。RTL为elaboration后的参数特化结果；不承诺导出的SV再有可独立override的parameter，脚本改变参数后必须重新生成。

`PEConfig`只接受PE_HQE_g4、PE_QE_g4、PE_H_g4、PE_Q_g4、PE_E_g4、PE_E_g2；wordCount=4*g，H/Q/E按支持族自动推导为wordCount/2wordCount/4wordCount，三模式互斥。groupCount仍决定packed输入和scale槽布局；H/Q的g4是兼容布局名，实际没有PG/SubPE实例。DesignConfig.top=pe/mn/k，pe/mn布局长度1，k为1–4。保存有序layout，禁止只由总容量认定同一个实现。

schema_version=2；top/layout必填，alignment可省略或部分填写，未知字段/非整数/重复CLI参数拒绝。无时钟或寄存器。固定格式码、bias、anchorW11、11/18级流水保持源合同；HiF4仍是待确认来源的实验编码。旧schema1不接受。
