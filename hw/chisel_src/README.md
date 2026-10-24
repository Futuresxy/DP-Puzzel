# Chisel 源码

当前实现迁移后的 PE、MN-PE 和 K-PE。源码按职责分目录、package 与目录对应；每个 Scala 文件对应 `hw/spec/` 下同路径、同名 Markdown。代码属于待审查版本，尚未进行 RTL 数值验证或 PPA 分析。

```text
chisel_src/
├── config/       dp.config：集中参数、格式选择与配置读取
├── common/       dp.common：接口、解码、移位/规约/LZD、FP32 基础单元
├── pe/           dp.pe：扁平的 PE 点积设计
├── core/         dp.core：MN-PE、K-PE 与共享 C/D 通路
└── elaborate/    dp.elaborate：检查、配置驱动生成、导出记录
```

目录是源码职责划分；硬件计算层级仍为 PE → MN/K-PE。common 中的 object 函数在调用位置展开，不重新引入 SubPE/PEGroup 层级。

| Scala 文件 | 对应 spec | 职责 |
| --- | --- | --- |
| [config/Parameters.scala](config/Parameters.scala) | [Parameters](../spec/config/Parameters.md) | 集中参数、实际 H/Q/E 容量和 JSON 顶层配置 |
| [config/Formats.scala](config/Formats.scala) | [Formats](../spec/config/Formats.md) | 格式编码、支持范围、A/B 兼容规则 |
| [common/Interfaces.scala](common/Interfaces.scala) | [Interfaces](../spec/common/Interfaces.md) | 数据、scale、特殊值、dot/C/D Bundle |
| [common/Decode.scala](common/Decode.scala) | [Decode](../spec/common/Decode.md) | 元素/scale/C 解码与特殊值分类 |
| [common/Arithmetic.scala](common/Arithmetic.scala) | [Arithmetic](../spec/common/Arithmetic.md) | 内联 MAX、移位、CSA、LZD、流水工具 |
| [pe/PE.scala](pe/PE.scala) | [PE](../spec/pe/PE.md) | 扁平的多格式共享点积与 scale 路径 |
| [common/Normalize.scala](common/Normalize.scala) | [Normalize](../spec/common/Normalize.md) | PE 无损规格化、FP32 舍入准备 |
| [core/Accumulate.scala](core/Accumulate.scala) | [Accumulate](../spec/core/Accumulate.md) | 顶层内联 C 加法及 D 公共数据通路 |
| [common/Fp32Pack.scala](common/Fp32Pack.scala) | [Fp32Pack](../spec/common/Fp32Pack.md) | 独立 FP32 舍入/打包基础模块 |
| [core/MNPE.scala](core/MNPE.scala) | [MNPE](../spec/core/MNPE.md) | 一个 PE 加 C，产生一个 D |
| [core/KPE.scala](core/KPE.scala) | [KPE](../spec/core/KPE.md) | 1–4 个 PE 在 K 方向规约，共享 C/D |
| [elaborate/Elaborate.scala](elaborate/Elaborate.scala) | [Elaborate](../spec/elaborate/Elaborate.md) | 仅供审查的结构展开入口 |
| [elaborate/Generate.scala](elaborate/Generate.scala) | [Generate](../spec/elaborate/Generate.md) | JSON 参数驱动的唯一 split RTL 导出入口 |

从 [迁移说明](../spec/pe-migration.md) 开始审查。旧参考工程只读保留；没有迁移旧 testbench、SystolicArray、环境变量配置、第三方 FPU 或已有 RTL/PPA 结果。

工具固定为 Mill 0.11.8、Scala 2.13.12、Chisel/plugin 6.4.0，定义在 [build.sc](../build.sc)。在 `hw/` 下使用已安装的 Mill 0.11.8：

```sh
mill -i pe.compile
mill -i pe.runMain dp.elaborate.Elaborate review
mill -i pe.runMain dp.elaborate.Elaborate mn H0Q0E32
mill -i pe.runMain dp.elaborate.Elaborate k H16Q32E64 H0Q32E0 H0Q0E64
mill -i pe.runMain dp.elaborate.Elaborate config configs/mn_h0q0e32.json
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/mn_h0q0e32.json "review E32"
```

当前机器也可用 `/home/songxy/.cache/mill/download/0.11.8` 代替 `mill`；该机器路径不参与构建配置。`review` 在内存生成 CHIRRTL 并列出模块，无 RTL 落盘、无数值仿真。`Generate` 根据参数将一 module 一文件的 RTL 存入唯一 [RTL 目录](../rtl/README.md)，记录 manifest/README/files.f；生成状态为 generated，不能进入 PPA。
