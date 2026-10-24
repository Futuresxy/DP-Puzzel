# Generate.scala：参数驱动的唯一 RTL 导出

对应源码：[Generate.scala](../../chisel_src/elaborate/Generate.scala)。Host-side 生成入口，不是硬件 Module。使用 [Parameters](../config/Parameters.md) 中的 DesignConfig 读取 JSON 后构造 MNPE 或 KPE。

```sh
cd hw
export CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin
mill -i pe.runMain dp.elaborate.Generate configs/mn_h0q0e32.json "source review export"
```

调整 h/q/e、align_width、kind 或有序 pes 列表，只改配置文件，不改 PE 电路源码。配置 schema 严格检查，MN 只能一个 PE，K 为 1–4 个；改变参数会在 elaboration 时改变资源、接口宽度和 top 名。非法配置在创建导出目录前拒绝。

导出位置固定为 `hw/rtl/<Top>__<config-id>__<UTC时间>__<source-sha12>/`，同名目录拒绝覆盖。config-id 是规范化有效参数 JSON 的 SHA-256 前缀，完整参数仍保存；source-sha 是 Scala 源文件、build.sc 和 .mill-version 的内容清单指纹，另外记录 Git commit 和 dirty 状态，避免未提交源码被误标为 commit 内容。

工具固定 Mill 0.11.8、Scala 2.13.12、Chisel 6.4.0、firtool 1.62.0；显式设置本机 firtool 目录，读取真实 --version，不记录机器私有路径。使用工具 split-verilog，检查每个 .sv 只有一个同名 module；将 PE、MNPE、KPE、Fp32Pack 的 RTL 定义映射到对应 Scala 文件。公共内联函数的逻辑属于调用模块，辅助源文件同样列入源码指纹。

每次导出生成：

- README：时间、原因、来源、状态和 manifest 导航；不能覆盖历史导出。
- manifest.json：有效参数、配置/源码 hash、工具版本、命令、模块映射、所有生成输入的路径和 hash。
- files.f：相对导出目录的 RTL 路径和 src include 搜索路径，自身也有 hash。
- src：每 module 一份 .sv；保留所需头文件，移除本次导出的 FIRRTL/注解中间文件。

状态从 generating 到 generated；`rtl_test=not_run`、`ppa_eligible=false`，没有任何接口把结构展开设为 passed。后续 SV/DC/power 必须从该目录读取，不复制设计 RTL，不使用“最新文件”隐式选择。

生成异常时删除本次 export 的 src/files.f，保留 failed manifest 和 README 供复现；不影响历史有效导出。导出前后重新核对源码指纹，防止边修改边生成导致来源不一致。后续验证门禁尚未实现，此文件不是 DC/power 调用入口。
