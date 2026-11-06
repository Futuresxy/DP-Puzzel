# 综合核心记录

此处只提交简洁 JSON：综合目的、时间、工艺/PVT、RTL 源码路径、run 路径、工具版本、频率、clock gating 状态，以及面积、setup/hold 结果。未知测量为 null，时序失败保留 FAIL 和负 slack。

完整约束、原始报告、网表和日志放在对应 runs 目录，不在 records 重复列出每个文件的指纹、工具文件、源码输入清单或验证矩阵。RTL 本身仅有一个目录指纹，由 export manifest 和回归证据关联。

从已核验 run 生成或更新记录：

```bash
bash scripts/dc_syn.sh report --run-id dc_dp_top_11050024 \
  --record dp_n12_1410mhz_20261105.json
```

报告核验不通过时不会写正式记录。records 不包含机器私有路径、凭据、PDK 或大型产物；生成后审查 diff，再显式提交。

新版 DP 记录另包含输入 RTL 的单个目录指纹、参数、关键路径/分级摘要、WNS/TNS 与 Vt 配额状态；不记录工具/库/报告/网表的逐文件指纹。实测明细见 [流水分析](dp_n12_timing_20261105.md)。

本机 `runs/` 保留 1.41 GHz 的 `dc_dp_top_11050024` 和 1 GHz 最终的 `dc_dp_top_11050215`。可直接读取其中的 `REPORT.md`、`reports/` 和 `netlist/`。原工作树清理前，将 1 GHz 首轮 `dc_dp_top_11050052` 和原 RTL 回执、输入快照归档到本机 `.cache/dp-dc-12nm-evidence.tar.gz`，并保留归档校验和。若要重新生成最终 1 GHz 的摘要，需先恢复其首轮 run 依赖。原始报告和配置快照保留运行时路径。

[E64 同工况对比](e64_n12_comparison_20261105.md)及[机器可读摘要](e64_n12_comparison_20261105.json)为用户确认的重要节点：E64 的有效 run 为 dc_dp_top_e_11052108，多精度 28/40 基线复测为 dc_dp_top_11052111。两者均用 N12 TT、1GHz、L8/II1；E 面积减少69.24%，但仍有一条 −0.307322ps setup 违例。E 首轮无效诊断及多精度首次有效测量另存；完整网表/日志只保留本地，精简 JSON 和分析进入 Git。

[E64 时序优先复测](e64_n12_timing_first_20261105.md)先核对 HiF4 token 坐标与 C 对齐，再在同一 RTL、库和1GHz预算下关闭显式面积回收。dc_dp_top_e_11052354 的 setup/hold/Vt 均通过，面积5686.972455µm²；S8余量+0.239730ps、全局最差+0.015974ps，仍无物理实现裕量保证。该 run 随本批重要结果长期保留，原失败结果不覆盖。
