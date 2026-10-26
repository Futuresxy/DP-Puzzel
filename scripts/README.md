# 公共流程入口职责

公共入口负责环境只读检查、固定依赖获取、带记录的RTL导出/检查、产物引用校验；完整RTL资格验证与EDA接入按各自实现状态记录，不能由有限检查代替。

所有入口读取明确配置和 ID，不使用隐式最新文件、不复制设计 RTL。EDA 入口只在挂载环境具备条件后运行。skill 应调用这些公共能力而非维护重复脚本。Git 日常同步依照开发流程，不未经审查自动提交所有文件。

当前 `check_full_reuse_export.py <export-id>` 只检查指定 full RTL 导出的来源清单、文件 hash、单 module 单文件与1–4/4/4实际层级，输出JSON摘要。它不会执行DUT或把generated提升为passed，不是后续PPA验证门禁。

当前六种PE使用 `check_pe_export.py <export-id> [--smoke]`。显式清单/hash与实际层级检查；smoke仅基础PE单位scale下−1/0/+1的数值坐标和11级valid。不会提升manifest状态，不是完整精度/PPA门禁。旧check_full_reuse_export仅检查历史Full导出。

当前结构检查要求H/Q没有DataUnpack/SubPE/PG实例，HQE/QE/E保留PG/SubPE；各PE直接实例化通用PENormalizeExact，不再允许Utils整条PE规约包装。旧结构的历史导出应结合其对应版本的检查器阅读。

`python scripts/check_pe_refactor.py <baseline-export-id> <candidate-export-id> [--seed 0x5eed27] [--samples 64]`验证两个显式导出的完整输入清单/hash、相同有效配置及接口，分别编译运行同一份SV testbench并逐拍比较结果/控制。覆盖所有合法格式对、一般编码/scale、特殊码、连续/气泡、在途复位；另独立检查PE 11级或K/MN 18级valid和last。输出在忽略的`hw/test/runs/pe-locality-<baseline>-vs-<candidate>/`，保存stimulus、TB、日志和带指纹报告，完成后删除仿真可执行文件。每组只接受新的run目录，避免覆盖证据。此脚本是抽样重构等价检查，基线不是独立精度oracle；不修改manifest、不允许PPA。当前批次见[记录](../hw/spec/pe-code-locality-checks.md)。
