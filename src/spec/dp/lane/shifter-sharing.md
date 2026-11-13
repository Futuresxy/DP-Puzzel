> 功能：lane 局部对齐与 E 旁路；范围：dp_top v1.8；QE/旧混合保持v1.7；版本：v1.8；修改时间：2026-11-09 17:59:28 +0800；对应代码：[dp_lane_align.v](../../../verilog/lane/dp_lane_align.v)；状态：已批准合同，CModel/RTL 已实现并通过本批功能验证。

# lane 局部对齐与 E 旁路

每lane四路LOCAL_W幅值右移器只服务T/H/Q；T/H/Q按group公共r计算delta，RTZ后恢复补码。INT8静态落位；E先符号化、窄pair，保持TC接入共享树，不进宽移位，不参与跨lane MAX。HiF4在S4 lane和末端先扩位再左移p=e2a+e2b；MX/NV固定补两零统一F4。参数化补零与符号扩展必须精确。

完整流水、自然位宽与门控合同见[主合同第2节](../dptop/dp-top-v1.8.md#2-e-lane-固定坐标)。旧QE和混合顶层通过静态兼容模式保留原实现；不得仅修改共用模块默认行为。
