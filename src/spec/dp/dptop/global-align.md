> 功能：全局比较指数与一次双向对齐；范围：dp_top v1.8；其他顶层保持v1.7；版本：v1.8；修改时间：2026-11-09 17:59:28 +0800；对应代码：[dp_global_align.v](../../../verilog/top/common/dp_global_align.v)；状态：已批准合同，CModel/RTL 已实现并通过本批功能验证。

# 全局比较指数与一次双向对齐

S5 group输出原幅值m、A_raw、compare_exp=A_raw-clz(m)、符号与分类；C直接输出compare_exp=A_raw，不进行LZD。非正规C保留0.xxx及A_raw=-126，零/特殊源不参与MAX。这是明确的数值策略变更，独立数学参考不变。

S6 Emax=max(active compare_exp)，signed_shift_delta=Emax-A_raw；正为右移、负为左移。原幅值静态低补零到GLOBAL_W-1，再仅做一次双向移位；无S5动态规格化。实现net=A_raw-Emax是反号等价形式。右移幅值RTZ后恢复TC；INT走静态旁路。差值用完整宽度，移出范围时清零。S6寄存叶子、共同指数及special/zero-sign。

比较指数不是所有源都真实规格化，因此不可假设MAX源首位必为1。S8仍按最终和重新LZD/RNE。详细接口、范围和验收见[主合同第4–7节](dp-top-v1.8.md)。
