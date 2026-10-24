# 可提交的综合记录

完整证据在被忽略的 `../runs/<run-id>/`，summary.json 为权威机器记录，summary.csv 为分析入口。当前没有真实测量，不创建占位面积或假 PASS。

形成可复现且通过适用检查的批次后，此处保存经审查的小型 `<run-id>.json/.csv`：schema、run/export/verification ID、源码 commit/差异指纹、DC 版本、工艺/PVT/约束、面积分项、setup/hold WNS/TNS/违例数/判定、未约束检查、netlist/SDC hash、限制、原始证据归档 URI 和归档 SHA-256。时序失败的测量必须保留失败状态。

本地 summary 含私有路径，不能直接复制提交。整理时去除本机工具/库/许可证/挂载路径，保留库标识和 hash，用受控归档 URI 替代本地位置；确认归档可恢复后显式 git add。不存在自动 publication 或 characterization 晋升。此目录不放 PDK、大网表、原始日志及超过 5 MiB 的文件。
