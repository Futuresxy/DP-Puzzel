# Chisel 源码：Full 复用四层实现

`hw/chisel_src/` 只保留 SubPE → PEGroupFull → MidGroupFull → PETile 这一实现，以及必要的配置和生成工具。没有 reuse 隔离目录，也不再并存扁平 PE/MN-PE/K-PE。来源与接口调整见 [迁移说明](../spec/full-reuse-migration.md)，结构检查见 [检查记录](../spec/full-reuse-checks.md)。

```text
config/       dp.config：唯一集中参数、格式与能力集合
common/       dp.common：移位、MAX、CSA、LZD 组合工具
pe/           dp.pe：SubPE、PEGroupFull、解包与固定点合同
core/         dp.core：MidGroupFull、PETile、共享C/D和规格化/舍入
elaborate/    dp.elaborate：结构检查与唯一split RTL导出
```

每个具体Module独立同名文件；每个Scala文件有镜像spec，Bundle/辅助object也包含在内。

| Scala 文件 | 对应 spec |
| --- | --- |
| [common/BalancedLeadingZero.scala](common/BalancedLeadingZero.scala) | [BalancedLeadingZero](../spec/common/BalancedLeadingZero.md) |
| [common/CarrySave.scala](common/CarrySave.scala) | [CarrySave](../spec/common/CarrySave.md) |
| [common/MaxLaneAlign.scala](common/MaxLaneAlign.scala) | [MaxLaneAlign](../spec/common/MaxLaneAlign.md) |
| [common/SignedShift.scala](common/SignedShift.scala) | [SignedShift](../spec/common/SignedShift.md) |
| [config/FormatCompat.scala](config/FormatCompat.scala) | [FormatCompat](../spec/config/FormatCompat.md) |
| [config/Parameters.scala](config/Parameters.scala) | [Parameters](../spec/config/Parameters.md) |
| [config/PrecisionConfig.scala](config/PrecisionConfig.scala) | [PrecisionConfig](../spec/config/PrecisionConfig.md) |
| [core/CUnpacker.scala](core/CUnpacker.scala) | [CUnpacker](../spec/core/CUnpacker.md) |
| [core/Interfaces.scala](core/Interfaces.scala) | [Interfaces](../spec/core/Interfaces.md) |
| [core/LeadingZeroCounter.scala](core/LeadingZeroCounter.scala) | [LeadingZeroCounter](../spec/core/LeadingZeroCounter.md) |
| [core/LzdNormalize.scala](core/LzdNormalize.scala) | [LzdNormalize](../spec/core/LzdNormalize.md) |
| [core/MidGroupAlignNormalize.scala](core/MidGroupAlignNormalize.scala) | [MidGroupAlignNormalize](../spec/core/MidGroupAlignNormalize.md) |
| [core/MidGroupFull.scala](core/MidGroupFull.scala) | [MidGroupFull](../spec/core/MidGroupFull.md) |
| [core/MidGroupInterfaces.scala](core/MidGroupInterfaces.scala) | [MidGroupInterfaces](../spec/core/MidGroupInterfaces.md) |
| [core/MidGroupNormalizeExact.scala](core/MidGroupNormalizeExact.scala) | [MidGroupNormalizeExact](../spec/core/MidGroupNormalizeExact.md) |
| [core/PETile.scala](core/PETile.scala) | [PETile](../spec/core/PETile.md) |
| [core/RoundIncrement.scala](core/RoundIncrement.scala) | [RoundIncrement](../spec/core/RoundIncrement.md) |
| [core/RoundPack.scala](core/RoundPack.scala) | [RoundPack](../spec/core/RoundPack.md) |
| [elaborate/Elaborate.scala](elaborate/Elaborate.scala) | [Elaborate](../spec/elaborate/Elaborate.md) |
| [elaborate/Generate.scala](elaborate/Generate.scala) | [Generate](../spec/elaborate/Generate.md) |
| [pe/DataUnpack.scala](pe/DataUnpack.scala) | [DataUnpack](../spec/pe/DataUnpack.md) |
| [pe/FixedPointMeta.scala](pe/FixedPointMeta.scala) | [FixedPointMeta](../spec/pe/FixedPointMeta.md) |
| [pe/PEGroupContract.scala](pe/PEGroupContract.scala) | [PEGroupContract](../spec/pe/PEGroupContract.md) |
| [pe/PEGroupFull.scala](pe/PEGroupFull.scala) | [PEGroupFull](../spec/pe/PEGroupFull.md) |
| [pe/PEGroupInterfaces.scala](pe/PEGroupInterfaces.scala) | [PEGroupInterfaces](../spec/pe/PEGroupInterfaces.md) |
| [pe/PEGroupMath.scala](pe/PEGroupMath.scala) | [PEGroupMath](../spec/pe/PEGroupMath.md) |
| [pe/SubPE.scala](pe/SubPE.scala) | [SubPE](../spec/pe/SubPE.md) |

```sh
cd hw
mill -i pe.compile
mill -i pe.runMain dp.elaborate.Elaborate review
mill -i pe.runMain dp.elaborate.Elaborate config configs/full_h48q96e192.json
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/full_h16q32e64.json "full reuse review"
```

工具固定为Mill0.11.8、Scala2.13.12、Chisel6.4.0、firtool1.62.0，定义在 [build.sc](../build.sc)。配置只开放完整MidGroup数和对齐窗口，详见 [configs](../configs/README.md)。生成RTL统一进入hw/rtl的独立导出目录。

当前只有编译/展开/导出结构证据，没有RTL数值通过记录、DC或power。原工程只读，未迁移阵列、旧RTL、专用精度variant、旧testbench/PPA或第三方FPU源码树。
