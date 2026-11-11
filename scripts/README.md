# 公共流程入口

- `rtl_gate.py EXPORT_ID` 校验 `hw/rtl/` 中的指定快照和 `test/runs/` 中的真实通过回执。
- `dc_syn.sh` 执行 DC 输入检查、准备、综合与报告。用法见 [DC 说明](../hw/dc_syn/README.md)。
- `research/` 保存外部参考平台的编译与分析工具。

设计维护在 `src/`，功能回归在 `test/`，综合和功耗分析在 `hw/`。入口使用明确的配置与 ID。

## 运行产物保留

日常 CModel、RTL 回归、DC 和功耗分别保留最近两次已结束且无引用的普通运行。回归目录按 UTC run ID 排序，DC 和功耗按终态完成时间排序。读完结果并记录所需证据后执行清理。

```sh
python3 scripts/run_retention.py           # 预览保留、跳过和待删除项
python3 scripts/run_retention.py --apply   # 删除超出名额的最旧普通运行
```

长期保留前先与用户确认具体 run ID 和理由，再在该运行目录写入保留标记。下面的路径应替换成确认过的真实运行目录。

```sh
python3 scripts/run_retention.py --pin 'test/runs/verilog/<run-id>' --reason '用户已确认的版本或里程碑'
```

标记、当前 RTL 门禁回执及验证范围、受 Git 跟踪或被项目记录、DC 和功耗元数据引用的运行均独立于普通名额保留。正在运行、未完成和无法识别的旧目录跳过。RTL manifest 的 `validation_runs` 记录历史回归范围，旧运行的原始文件可随滚动策略到期。

清理范围限于 Git 忽略的 `test/runs/cmodel/`、`test/runs/verilog/`、`hw/dc_syn/runs/` 和 `hw/power/runs/` 下的运行目录。长期证据按项目规则提交精简摘要，大文件可用带校验和的本地归档或外部归档。功耗运行以 `.running` 标记活动阶段，写入终态 `state.json`，包含 `phase=finished` 或 `failed` 和 UTC `finished_utc`（格式 `YYYYMMDDTHHMMSSffffffZ`）。对所用 DC run 的引用写入本次功耗运行的 `manifest.json` 或 `inputs/resolved.json`。
