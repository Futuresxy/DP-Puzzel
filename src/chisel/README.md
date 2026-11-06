# Chisel

状态：已建立共用 [spec](../spec/README.md) 和 CModel，Chisel 源码与构建入口待实施。

实现已确认的微架构、有限位宽算法、流水与协议。每个模块关联对应 spec；资源共享、截断或周期变化先更新合同。生成的 RTL 放入 `hw/rtl/<export-id>/`，与手写 Verilog 的导出分别追踪。

共用验证入口为根目录 [test/](../../test/README.md)。历史五族 PE、参数及流水不作为本目录默认约束。

**v1.1 参数与模块约定：** 计划以 src/chisel/parameter/ 为集中参数入口（尚未创建文件），通过模块构造参数向 T1H2Q4E8、T2H4Q8E16 与顶层传递有效配置。算术宽度、补零、移位控制、树层数与自然增长均按公式派生；只在 spec 中确定这些合同，当前不编写 Scala/RTL。

**v1.2 接口与统计：** [DP 接口](../spec/dp/dptop/interface.md) 与 [逐请求控制](../spec/dp/dptop/control.md) 替代稳定批次 cfg；S5 解包 C。按 [共享移位器](../spec/dp/lane/shifter-sharing.md) 实例化固定参数宽度单元、输入 mux 选格式；按 [功能统计](../spec/dp/implementation/resource-accounting.md) 建立 Module/实例/寄存归属映射，保持同一八级边界。当前仍无实现。

**定点格式与窗口参数。** 构建配置传入 `kFp16`、`localShiftMagWidth` 和 `globalSignedAlignWidth`，默认 16/28/40。由参数派生叶宽、lane/组 SOP 宽、LZD 位数、补零和加法增长位。每个模块在乘法器、移位器、加法树的输入与输出以及级间端口注释各支持格式的 `SxIxFx`，标出二补码、独立符号与幅值、结构低零以及参考指数。每个树节点增加整数位并保留 F，顶层增长 `ceil(log2(kFp16/4+1))` 位。格式按 [逐级出口表](../spec/dp/common/stage-formats.md) 和 [参数合同](../spec/06-configuration.md) 推导。

格式注释按对齐表格书写，每行一种或一类精度，分别列出 S、I、F。表前定义使用的参数和符号表示方式，乘法器输入与输出分别列出对应的 S、I、F。
