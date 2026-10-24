# 硬件规格

当前入口：[六种PE设计](six-pe-design.md)、[检查记录](six-pe-checks.md)、[固定版本来源](six-pe-source.json)、[集中参数](config/Parameters.md)。

五族逐文件spec在pe/PE_H、PE_Q、PE_E、PE_HQE、PE_QE；公共算术/接口/C-D在Utils；core为K_PE/MN_PE；elaborate为统一检查/生成。每个Scala都有镜像spec，包含数值坐标、资源、周期和验收边界。完整索引见 [源码导航](../chisel_src/README.md)。

full-reuse-*、pe-migration/migration-checks是此前历史迁移记录，不能混作当前验证证据。阵列只调研讨论，无实现。完整SV数值回归、EDA与characterization未完成。
