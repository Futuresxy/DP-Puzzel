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

混合组 v1.7.1 的同工况结果见 [L8 / 1GHz 面积与时序比较](mixed_n12_1000mhz_20261108.md)。比较入口要求基线与三个混合顶层使用一致的库、PVT、参数、工具和最终约束，并核验真实门控与八级报告。可用以下命令从保留的本地运行重新生成：

```bash
python3.11 hw/dc_syn/scripts/compare_mixed.py \
  --run dc_dp_top_11080044 \
  --run dc_dp_top_t8h16q32e96_11080048 \
  --run dc_dp_top_t8h16q32e128_11080056 \
  --run dc_dp_top_t8h16q64e128_11080147 \
  --record mixed_n12_1000mhz_20261108
```

比较 JSON 逐设计记录源检查点关联的 export/verification、容量、面积变化、setup/hold、各级关键路径、ICG 数量及寄存器门控比例。Q/E 容量除以面积的相对值只表示该模式原生 K 的面积效率；不能作为负载功耗或芯片吞吐测量。修复源运行由最终运行引用，清理时一并保护。

QE 首轮优化见 [最终 1GHz / 面积比较](qe_area_opt_n12_1000mhz_20261108.md)：固定字段解包、S1 配对摘要与扩展源浮点选择；最终 28191.89 µm²，相对基础 DP +66.53%，setup/hold/VT/电气规则通过。用户接受本轮约66%增幅。[初次 run](qe_area_opt_n12_1000mhz_initial_20261108.md)保留 hold 失败及修复来源；比较脚本为 `scripts/compare_qe_area.py`，历史输入按冻结快照/原回执核验，新输入按当前完整门禁核验。
