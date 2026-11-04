# Chisel

状态：等待整体 [spec](../spec/README.md) 和 CModel，当前没有 RTL 设计代码或构建入口。

实现已确认的微架构、有限位宽算法、流水与协议。每个模块关联对应 spec；资源共享、截断或周期变化先更新合同。生成的 RTL 放入 `hw/rtl/<export-id>/`，与手写 Verilog 的导出分别追踪。

共用验证入口为根目录 [test/](../../test/README.md)。历史五族 PE、参数及流水不作为本目录默认约束。
