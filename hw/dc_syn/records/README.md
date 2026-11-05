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
