> 功能：dp_top 八级流水；范围：dp_top v1.8；其他族维持原流水；版本：v1.8；修改时间：2026-11-09 17:59:28 +0800；对应代码：[dp_top.v](../../../verilog/top/dp_top.v)；状态：已批准合同，CModel/RTL 已实现并通过本批功能验证。

# dp_top 八级流水

L8/II=1、逐拍换型、同步rst_n；valid每拍推进，payload按有效使能更新。沿n接收于S1，沿n+7更新S8；验证观察相位保持原合同。所有新增组合算术都不暗加寄存器。

逐级操作以[主合同流水表](dp-top-v1.8.md#1-流水与数值)为唯一当前定义。S2 group MAX仅T/H/Q；S3 E pair及提前anchor；S4共享树/HiF小左移；S5组和/scale/LZD/compare_exp；S6单次双向移位和符号恢复；S7 4:2+3:2+CPA；S8编码。

C raw32延迟至S5，不复制到group；scale从S1独立预计算。S3/S4的A_raw、HiF p、type/valid、special/zero-sign必须随同一请求推进。备用L9若保留软件探索不得冒充已验证RTL。当前新设计PPA待测。
