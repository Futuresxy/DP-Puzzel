> 功能：scale 无偏解包与提前 anchor；范围：dp_top v1.8；版本：v1.8；修改时间：2026-11-09 17:59:28 +0800；对应代码：[dp_group.v](../../../verilog/group/dp_group.v)、[dp_scale_unpack.v](../../../verilog/unpack/dp_scale_unpack.v)；状态：已批准合同，CModel/RTL 已实现并通过本批功能验证。

# scale 无偏解包与提前 anchor

S1 scale输出无符号I1F3和signed8无偏指数；E8M0 raw-127，E4M3有效指数-7，E6M2 raw-48，无scale为0。特殊值独立保存。S2 4×4系数积为I2F6，指数先扩位再signed9相加。S3计算A_raw并寄存，S4传递；S5组和/abs后只有NV/HiF走14×8乘法，MX旁路幅值乘法、保留指数缩放。

A_raw=r_effective+scale_exp_sum+(M_group-1-F_group-2*element_bias)。T/H/Q使用公共r；E使用0。F_group由最终S5幅值小数点决定。S5再计算compare_exp=A_raw-z，保留未移动magnitude；零/特殊源屏蔽。详细位宽与兼容范围见[主合同](../dptop/dp-top-v1.8.md)。其他顶层的旧biased scale接口保持，避免重复或漏扣bias。
