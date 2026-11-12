# 结果与归档

面积和 GEMM 完整运行目录默认由 Git 忽略。每个目录含 `manifest.json`，记录命令、配置、输入/源码/输出 SHA-256 及模型版本。文件写入完成后生成 manifest，自动化可将其作为完成标记。复现运行使用新目录。

仅经过选择、可复现的核心摘要放在 summaries/；图表放 figures/ 并附生成配置，较大文件使用外部归档 URI + SHA-256。已引用结果禁止随意覆盖；新增关键数据及时走 commit/push/PR。

样例见 [快速启动](../README.md#quick-start)。下游芯片搜索的 Pareto 结果使用同样的来源和归档约定。
