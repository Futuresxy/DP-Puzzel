# 顶层共用实现模块

`top/` 根目录仅放六种架构入口和 `dp_top_e` 兼容入口；此目录放顶层复用核心及后端组合模块。

| 模块 | 职责 | 使用者 |
| --- | --- | --- |
| dp_top_mixed | 基础四组＋E/QE扩展、C流水、分支规约与输出 | E96、E128、优化Q64E128三个固定包装 |
| dp_top_lowp | 静态选择四组E/QE、C流水及五源浮点后端 | E64、Q32E64两个固定包装 |
| dp_global_align | 所有源参加的MAX、移位、符号恢复与特殊值归约 | dp_top、dp_top_e、dp_top_lowp |
| dp_mixed_global_align | 带逐请求参与屏蔽的基础/扩展分支全局对齐 | dp_top_mixed |

这些文件不是额外的容量配置。通过 `src/verilog/files*.f` 显式选择对外顶层和依赖，不直接把common目录当作综合入口。模块名/端口保持原样；搬移会改变源码清单指纹，新的EDA运行需要重新导出和验证，不能修改旧快照。

架构差异和逐模块spec导航见 [top-architectures.md](../../../spec/dp/dptop/top-architectures.md)。
