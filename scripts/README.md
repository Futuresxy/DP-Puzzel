# 公共流程入口职责

已实现 `rtl_gate.py EXPORT_ID` 只读验证门禁，以及 `bash scripts/dc_syn.sh` 的 check/prepare/run/report/clean 入口，使用说明见 [DC 流程](../hw/dc_syn/README.md)。check/prepare 不运行 EDA；真实 run 仅在获准挂载环境执行。

`dc_example.py export/verify/run` 是用户授权的 BF16 最小例子入口：逐字节导出手写源、真实 SV 回归及证据生产，再调用公共 DC 流程。固定依赖获取、完整 Chisel exporter、通用研究硬件回归和功耗入口仍待实施。

所有入口读取明确配置和 ID，不使用隐式最新文件、不复制设计 RTL。EDA 入口只在挂载环境具备条件后运行。skill 应调用这些公共能力而非维护重复脚本。Git 日常同步依照开发流程，不未经审查自动提交所有文件。
