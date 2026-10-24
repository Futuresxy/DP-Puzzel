# 五族六种基础 PE

当前唯一实现分为H/Q/E/HQE/QE五族，原MidGroup称PE。HQE/QE/E保留分级复用，H/Q采用16/32路全局对齐。PE_E一个源码导出g2/g4；六种PE输出F与周期一致，参数化K_PE/MN_PE共享C/D。不含阵列实现。

入口：[设计与参数合同](../spec/six-pe-design.md)、[检查记录](../spec/six-pe-checks.md)、[配置](../configs/README.md)。

| Scala | spec |
| --- | --- |
| [Utils/BalancedLeadingZero.scala](Utils/BalancedLeadingZero.scala) | [BalancedLeadingZero](../spec/Utils/BalancedLeadingZero.md) |
| [Utils/CUnpacker.scala](Utils/CUnpacker.scala) | [CUnpacker](../spec/Utils/CUnpacker.md) |
| [Utils/CarrySave.scala](Utils/CarrySave.scala) | [CarrySave](../spec/Utils/CarrySave.md) |
| [Utils/DecodeInterfaces.scala](Utils/DecodeInterfaces.scala) | [DecodeInterfaces](../spec/Utils/DecodeInterfaces.md) |
| [Utils/DecodePrimitives.scala](Utils/DecodePrimitives.scala) | [DecodePrimitives](../spec/Utils/DecodePrimitives.md) |
| [Utils/DotUnit.scala](Utils/DotUnit.scala) | [DotUnit](../spec/Utils/DotUnit.md) |
| [Utils/FixedPointMeta.scala](Utils/FixedPointMeta.scala) | [FixedPointMeta](../spec/Utils/FixedPointMeta.md) |
| [Utils/Interfaces.scala](Utils/Interfaces.scala) | [Interfaces](../spec/Utils/Interfaces.md) |
| [Utils/LeadingZeroCounter.scala](Utils/LeadingZeroCounter.scala) | [LeadingZeroCounter](../spec/Utils/LeadingZeroCounter.md) |
| [Utils/LzdNormalize.scala](Utils/LzdNormalize.scala) | [LzdNormalize](../spec/Utils/LzdNormalize.md) |
| [Utils/MaxLaneAlign.scala](Utils/MaxLaneAlign.scala) | [MaxLaneAlign](../spec/Utils/MaxLaneAlign.md) |
| [Utils/PEAlignNormalize.scala](Utils/PEAlignNormalize.scala) | [PEAlignNormalize](../spec/Utils/PEAlignNormalize.md) |
| [Utils/PEFactory.scala](Utils/PEFactory.scala) | [PEFactory](../spec/Utils/PEFactory.md) |
| [Utils/PEGlobalAlignNormalize.scala](Utils/PEGlobalAlignNormalize.scala) | [PEGlobalAlignNormalize](../spec/Utils/PEGlobalAlignNormalize.md) |
| [Utils/PEGroupContract.scala](Utils/PEGroupContract.scala) | [PEGroupContract](../spec/Utils/PEGroupContract.md) |
| [Utils/PEGroupInterfaces.scala](Utils/PEGroupInterfaces.scala) | [PEGroupInterfaces](../spec/Utils/PEGroupInterfaces.md) |
| [Utils/PEGroupMath.scala](Utils/PEGroupMath.scala) | [PEGroupMath](../spec/Utils/PEGroupMath.md) |
| [Utils/PEInterfaces.scala](Utils/PEInterfaces.scala) | [PEInterfaces](../spec/Utils/PEInterfaces.md) |
| [Utils/PENormalizeExact.scala](Utils/PENormalizeExact.scala) | [PENormalizeExact](../spec/Utils/PENormalizeExact.md) |
| [Utils/PEWiring.scala](Utils/PEWiring.scala) | [PEWiring](../spec/Utils/PEWiring.md) |
| [Utils/RawProductInterfaces.scala](Utils/RawProductInterfaces.scala) | [RawProductInterfaces](../spec/Utils/RawProductInterfaces.md) |
| [Utils/RoundIncrement.scala](Utils/RoundIncrement.scala) | [RoundIncrement](../spec/Utils/RoundIncrement.md) |
| [Utils/RoundPack.scala](Utils/RoundPack.scala) | [RoundPack](../spec/Utils/RoundPack.md) |
| [Utils/SignedShift.scala](Utils/SignedShift.scala) | [SignedShift](../spec/Utils/SignedShift.md) |
| [Utils/SubPEInterfaces.scala](Utils/SubPEInterfaces.scala) | [SubPEInterfaces](../spec/Utils/SubPEInterfaces.md) |
| [config/FormatCompat.scala](config/FormatCompat.scala) | [FormatCompat](../spec/config/FormatCompat.md) |
| [config/Parameters.scala](config/Parameters.scala) | [Parameters](../spec/config/Parameters.md) |
| [config/PrecisionConfig.scala](config/PrecisionConfig.scala) | [PrecisionConfig](../spec/config/PrecisionConfig.md) |
| [core/K_PE.scala](core/K_PE.scala) | [K_PE](../spec/core/K_PE.md) |
| [core/MN_PE.scala](core/MN_PE.scala) | [MN_PE](../spec/core/MN_PE.md) |
| [elaborate/Elaborate.scala](elaborate/Elaborate.scala) | [Elaborate](../spec/elaborate/Elaborate.md) |
| [elaborate/Generate.scala](elaborate/Generate.scala) | [Generate](../spec/elaborate/Generate.md) |
| [pe/PE_E/DataUnpack_E.scala](pe/PE_E/DataUnpack_E.scala) | [DataUnpack_E](../spec/pe/PE_E/DataUnpack_E.md) |
| [pe/PE_E/PEGroup_E.scala](pe/PE_E/PEGroup_E.scala) | [PEGroup_E](../spec/pe/PE_E/PEGroup_E.md) |
| [pe/PE_E/PE_E.scala](pe/PE_E/PE_E.scala) | [PE_E](../spec/pe/PE_E/PE_E.md) |
| [pe/PE_E/SubPE_E.scala](pe/PE_E/SubPE_E.scala) | [SubPE_E](../spec/pe/PE_E/SubPE_E.md) |
| [pe/PE_H/DataUnpack_H.scala](pe/PE_H/DataUnpack_H.scala) | [DataUnpack_H](../spec/pe/PE_H/DataUnpack_H.md) |
| [pe/PE_H/PEGroup_H.scala](pe/PE_H/PEGroup_H.scala) | [PEGroup_H](../spec/pe/PE_H/PEGroup_H.md) |
| [pe/PE_H/PE_H.scala](pe/PE_H/PE_H.scala) | [PE_H](../spec/pe/PE_H/PE_H.md) |
| [pe/PE_H/SubPE_H.scala](pe/PE_H/SubPE_H.scala) | [SubPE_H](../spec/pe/PE_H/SubPE_H.md) |
| [pe/PE_HQE/DataUnpack_HQE.scala](pe/PE_HQE/DataUnpack_HQE.scala) | [DataUnpack_HQE](../spec/pe/PE_HQE/DataUnpack_HQE.md) |
| [pe/PE_HQE/PEGroup_HQE.scala](pe/PE_HQE/PEGroup_HQE.scala) | [PEGroup_HQE](../spec/pe/PE_HQE/PEGroup_HQE.md) |
| [pe/PE_HQE/PE_HQE.scala](pe/PE_HQE/PE_HQE.scala) | [PE_HQE](../spec/pe/PE_HQE/PE_HQE.md) |
| [pe/PE_HQE/SubPE_HQE.scala](pe/PE_HQE/SubPE_HQE.scala) | [SubPE_HQE](../spec/pe/PE_HQE/SubPE_HQE.md) |
| [pe/PE_Q/DataUnpack_Q.scala](pe/PE_Q/DataUnpack_Q.scala) | [DataUnpack_Q](../spec/pe/PE_Q/DataUnpack_Q.md) |
| [pe/PE_Q/PEGroup_Q.scala](pe/PE_Q/PEGroup_Q.scala) | [PEGroup_Q](../spec/pe/PE_Q/PEGroup_Q.md) |
| [pe/PE_Q/PE_Q.scala](pe/PE_Q/PE_Q.scala) | [PE_Q](../spec/pe/PE_Q/PE_Q.md) |
| [pe/PE_Q/SubPE_Q.scala](pe/PE_Q/SubPE_Q.scala) | [SubPE_Q](../spec/pe/PE_Q/SubPE_Q.md) |
| [pe/PE_QE/DataUnpack_QE.scala](pe/PE_QE/DataUnpack_QE.scala) | [DataUnpack_QE](../spec/pe/PE_QE/DataUnpack_QE.md) |
| [pe/PE_QE/PEGroup_QE.scala](pe/PE_QE/PEGroup_QE.scala) | [PEGroup_QE](../spec/pe/PE_QE/PEGroup_QE.md) |
| [pe/PE_QE/PE_QE.scala](pe/PE_QE/PE_QE.scala) | [PE_QE](../spec/pe/PE_QE/PE_QE.md) |
| [pe/PE_QE/SubPE_QE.scala](pe/PE_QE/SubPE_QE.scala) | [SubPE_QE](../spec/pe/PE_QE/SubPE_QE.md) |

```sh
cd hw
mill -i pe.compile
mill -i pe.runMain dp.elaborate.Elaborate review
mill -i pe.runMain dp.elaborate.Elaborate config configs/pe_e_g2.json --pe-align-width 44 --top-align-width 44
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/k_1_2_6.json "six PE review"
```

工具固定Mill0.11.8、Scala2.13.12、Chisel6.4.0、firtool1.62.0。参数在生成时特化，导出RTL不能任意再override未知SV parameter；选择新参数后重新导出。当前未完成全格式数值回归或PPA。
