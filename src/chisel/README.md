# Chisel

状态：等待整体 [spec](../spec/README.md) 和 CModel，当前没有 RTL 设计代码或构建入口。

实现已确认的微架构、有限位宽算法、流水与协议。每个模块关联对应 spec；资源共享、截断或周期变化先更新合同。生成的 RTL 放入 `hw/rtl/<export-id>/`，与手写 Verilog 的导出分别追踪。

共用验证入口为根目录 [test/](../../test/README.md)。历史五族 PE、参数及流水不作为本目录默认约束。

**v1.1 参数与模块约定：** 计划以 src/chisel/parameter/ 为集中参数入口（尚未创建文件），通过模块构造参数向 T1H2Q4E8、T2H4Q8E16 与顶层传递有效配置。算术宽度、补零、移位控制、树层数与自然增长均按公式派生；只在 spec 中确定这些合同，当前不编写 Scala/RTL。

**v1.2 接口与统计：** [DP 接口](../spec/dp/interface.md) 与 [逐请求控制](../spec/dp/control.md) 替代稳定批次 cfg；S5 解包 C。按 [共享移位器](../spec/dp/shifter-sharing.md) 实例化固定参数宽度单元、输入 mux 选格式；按 [功能统计](../spec/dp/resource-accounting.md) 建立 Module/实例/寄存归属映射，保持同一八级边界。当前仍无实现。
