# 外部依赖与本地参考

ref_work/ 是本地参考工作区，整体忽略；可用于阅读、优化和方案对比，不自动成为正式依赖，也不由项目清理流程删除。

CACTI 等项目作为依赖接入时，仓库只保存来源、固定版本、许可证、必要补丁和 adapter，不把第三方源码树复制到项目源码中。实际源码在使用前 clone/download 到被忽略的 .deps/<name>/。

实施阶段的版本清单应记录：name、upstream URL、完整 commit 或带 hash 的 release、license、用途、获取方式、构建说明、补丁及输入输出单位。禁止正式实验依赖浮动 main/master。第三方构建产物放在 .deps 或 run 目录。

当前没有引入 CACTI 等建模依赖；接入前应明确建模对象、工艺适用范围、容量/端口/带宽与结果误差。缓存/SRAM 模型不能自动代替 HBM、全部互连或整芯片成本。

Ascend ISA 调研使用直接克隆的官方 `cann/asc-devkit` 和官方 CANN 9.1.0 编译组件，固定来源、commit/release及校验和见 [ascend-research.json](ascend-research.json)。它们只用于外部 ISA 的源码分析与编译探针，不进入本项目 Chisel/RTL 构建或 characterization。完整第三方源码、二进制工具和编译产物分别保存在被忽略的 `.deps/`、`.cache/`。

Chisel 构建使用 Maven 发布依赖，由 Mill/Coursier 获取并缓存，源码没有 vendoring：Mill 0.11.8、Scala 2.13.12、Chisel/plugin 6.4.0、os-lib 0.9.1、ujson 3.1.0，具体坐标在 [hw/build.sc](../hw/build.sc)；RTL 生成器要求 firtool 1.62.0。版本与有效工具字符串随导出 manifest 保存。本机已有缓存，不从旧工程复制构建产物或 FPU 依赖。

AI 首层数据准备的模型、tokenizer 和 WikiText-2 test 固定来源统一在 [data/sources.json](../hw/test/data/sources.json)，用途、许可证和获取方式见 [数据说明](../hw/test/data/README.md)。工具使用安装的 Transformers 4.56.0 及其官方模块，Python 版本清单见 [requirements.txt](../hw/test/data/requirements.txt)；不复制第三方源码。模型元数据位于 `.deps/`，按字节读取的权重缓存、原始采集及量化产物位于被忽略的 `hw/test/data/cache/` 与 `artifacts/`。数据数值单位为各格式表示的实数，MAC 按一次乘加计数，2 OP/MAC；没有外部工具测量的 PPA 数据。
