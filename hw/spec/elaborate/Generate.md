# Generate.scala：唯一 full RTL 导出

对应源码：[Generate.scala](../../chisel_src/elaborate/Generate.scala)。Host-side main，读取 [DesignConfig](../config/Parameters.md)，通过共用Elaborate.module构造当前唯一PETile。参数只有mid_groups与align_width，不再支持旧kind/pes或mn/k顶层。

```sh
cd hw
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/full_h16q32e64.json "full source review"
```

配置非法或reason为空，在创建导出目录前拒绝。工具固定Mill0.11.8、Scala2.13.12、Chisel6.4.0和firtool1.62.0；CHISEL_FIRTOOL_PATH只指定工具位置，不改变电路参数。读取实际tool --version核对，不记录私有工具路径。

导出固定为 `hw/rtl/<Top>__<config-id>__<UTC微秒时间>__<source-sha12>/`，重复目录拒绝覆盖。config-id来自规范化有效JSON；source hash来自排序后的全部Scala/build.sc/.mill-version路径与SHA-256清单，同时记录Git commit与dirty。导出前后比较源码，防止修改过程中产生混合指纹。

split-verilog由编译器生成，每个.sv必须恰好一个同名module。全部12类具体模块映射到dp.config/common/pe/core下相应源码类（实际Module在pe/core），保留SubPE/PEGroupFull/MidGroupFull/PETile四层模块名检查。每项module记录Chisel类、源码路径、完整顶层参数和RTL hash；局部固定参数由对应spec及source指纹界定。

每个export含README、manifest.json、files.f和src。manifest记录工具/命令/参数/源码/module/输入文件hash；files.f为相对路径并记录自身hash。共享module定义只保留一次，但物理实例不因定义去重而共享。工具中间FIRRTL/anno可在本次目录清理，保留必要RTL/辅助输入。

异常时删本次src/files.f，保留failed README/manifest和错误，不改旧导出。成功仅为generated，rtl_test=not_run、ppa_eligible=false；不能因结构生成成功写passed。

从仓库根执行 `python scripts/check_full_reuse_export.py <export-id>`，只检查显式指定导出的hash、清单、单module文件和实际1/N/4N/16N层级。该工具不执行DUT或改变验证状态，不是SV精度或PPA门禁。后续SV/DC/power必须继续解析同一export清单，不复制RTL或隐式选择最新文件。
