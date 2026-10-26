# 六种PE及K/MN唯一RTL导出

对应源码：[Generate.scala](../../chisel_src/elaborate/Generate.scala)。

用法：Generate <config.json> <reason> [--q-align-width N --group-guard-bits N --pe-align-width N --top-align-width N]。读取schema2配置，Parameters默认<JSON<CLI，验证后才创建唯一export；记录完整有效配置和命令。

固定Mill0.11.8/Scala2.13.12/Chisel6.4.0/firtool1.62.0。编译器split-verilog；加disallowLocalVariables以兼容本机Icarus，不修改生成RTL。

导出目录按用户要求简化为`K-PE_H16Q32E96_10241548`、`MN-PE_H0Q32E0_10241548`；基础PE为`PE_E_g2_10241548`。末尾为Asia/Singapore的`MMddHHmm`（月日时分），不再把配置hash、源码hash或位宽后缀拼入目录。完整年份/UTC时间、时区、layout、有效参数、config_id和全源码hash仍进manifest。同容量/同分钟的不同参数或重复导出也会重名，生成前拒绝覆盖并提示稍后一分钟重试；不自动选择旧导出。

内部module名及同名.sv保持合法稳定的SystemVerilog标识符，例如`K_PE_H16Q32E96.sv`；目录使用的连字符与时间不加入module名。每module一同名.sv，映射dp.pe.h/q/e/hqe/qe、dp.utils及dp.core真实类与文件，记录SHA-256、来源commit/dirty；导出前后校验source不变。H/Q仅映射PE文件，已删除的SubPE/PG/DataUnpack和Utils整条PE规约不再是合法当前模块映射；通用PENormalizeExact仍有独立源码映射。

README/manifest/files.f/src完整，相对filelist与所有输入有hash。异常删除本次src/files.f保留failed记录。成功始终generated、rtl_test=not_run、ppa_eligible=false；有限smoke不能提升为passed。scripts/check_pe_export.py校验显式export并可运行基础PE定向单位值/坐标/11级valid检查，完整回归/验证门禁与PPA另行实现。
