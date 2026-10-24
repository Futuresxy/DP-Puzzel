# 五族能力集合

对应源码：[PrecisionConfig.scala](../../chisel_src/config/PrecisionConfig.scala)。

Precision.h/q/e/hqe/qe是五种封闭profile派生的能力。H支持FP16/BF16；Q支持E5M2/E4M3/E3M2/E2M3；E支持E2M1/NVFP4/HiF4；HQE和QE为相应并集。PEPrecisionConfig只作为内部host元信息，不对JSON开放任意布尔组合。

supportsDataTypeCode为host查询，supportsDataType生成组合W4比较，必须与FormatCompat的A/B合法对及scale配对共同使用；支持两个格式不意味着任意交叉相乘合法。无状态/复位/流水。待SV完整覆盖编码拒绝、混合Q、混合E2M1/NV及特殊值；当前定向smoke不是完整精度回归。
