# 综合核心记录

此处只提交简洁 JSON：综合目的、时间、工艺/PVT、RTL 源码路径、run 路径、工具版本、频率、clock gating 状态，以及面积、setup/hold 结果。未知测量为 null，时序失败保留 FAIL 和负 slack。

完整约束、原始报告、网表和日志放在对应 runs 目录，不在 records 重复列出每个文件的指纹、工具文件、源码输入清单或验证矩阵。RTL 本身仅有一个目录指纹，由 export manifest 和回归证据关联。

从已核验 run 生成或更新记录：

```bash
bash scripts/dc_syn.sh report --run-id dc_Bf16SignPipe_10241850 \
  --record bf16_sign_pipe_smoke_20261024.json
```

报告核验不通过时不会写正式记录。records 不包含机器私有路径、凭据、PDK 或大型产物；生成后审查 diff，再显式提交。
