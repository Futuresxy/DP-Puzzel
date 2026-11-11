# DC 实验记录与最新结果

当前验收批次：2026-11-10，基础 dp_top v1.8 修复版、三个混合顶层及 Q32E64 v1.9、E64 原设计。**日常查面积与时序先看本页。**

工况：N12 TT / 0.7 V / 85°C，1 GHz，L8 / II=1，LOCAL28 / GLOBAL40，ICG 开启。综合后、CTS/布线前；setup 正余量很小，不是多角物理签核。

## 最新六种 DP

[完整面积/时序报告](v19_six_dp_20261110.md) · [JSON及来源指纹](v19_six_dp_20261110.json) · [功耗记录入口](../../power/records/README.md) · [七类面积图](../../../paper/data/H16Q32E64_area/README.md)

| 架构 | 面积 µm² | setup / hold / 电气 | 最新工作目录 |
|---|---:|---|---|
| T8H16Q32E64 | 16165.122 | PASS / PASS / PASS | [dc_dp_top_11092301](../runs/dc_dp_top_11092301/) |
| T8H16Q32E96 | 18863.272 | PASS / PASS / PASS | [dc_dp_top_t8h16q32e96_11092351](../runs/dc_dp_top_t8h16q32e96_11092351/) |
| T8H16Q32E128 | 21596.406 | PASS / PASS / PASS | [dc_dp_top_t8h16q32e128_11092351](../runs/dc_dp_top_t8h16q32e128_11092351/) |
| T8H16Q64E128 opt | 27191.145 | PASS / PASS / PASS | [dc_dp_top_t8h16q64e128_opt_11092351](../runs/dc_dp_top_t8h16q64e128_opt_11092351/) |
| E64 | 5644.136 | PASS / PASS / PASS | [dc_dp_top_e64_11080854](../runs/dc_dp_top_e64_11080854/) |
| Q32E64 | 11695.215 | PASS / PASS / PASS | [dc_dp_top_q32e64_11092358](../runs/dc_dp_top_q32e64_11092358/) |

工作目录内：`reports/` 查看面积/时序/电气，`netlist/` 保存网表、DDC、SDC，`inputs/resolved.json` 绑定 RTL 快照、参数、工况和原验证回执。

`runs/` 仅包含表中的六份最终结果。基线电气违例运行 `dc_dp_top_11091816` 和 Q32E64 hold 违例运行 `dc_dp_top_q32e64_11092350` 已删除。最终报告保留修复来源，已完成结果的汇总复核使用[清理前的修复链回执](../maintenance/final_six_dependency_retirement.json)。原增量修复需要重新生成对应的修复输入。

## 历史数值与对比

2026-11-10 用户授权清理历史运行大产物。**本目录历史 MD/JSON/CSV 全部保留；旧报告中的 runs 链接不保证仍存在。历史数值可比较，已清理批次不能再声称具备完整本地复现材料。**

| 实验 | 记录 | 原始产物状态 |
|---|---|---|
| v1.9 六架构 | [面积与时序](v19_six_dp_20261110.md) | 六份最终运行保留 |
| v1.8 电气修复 | [修复记录](dp_top_v18_electrical_repair_20261109.md) | 保留，为当前 baseline |
| v1.8 首次综合 | [首次记录](dp_top_v18_n12_1000mhz_20261109.md) | 原电气违例运行已删除 |
| 固定解包优化 | [优化对比](fixed_unpack_20261109.md) | 旧 run 已清理 |
| 原精度门控六架构 | [旧汇总](latest_six_dp.md) | 大产物已清理，E64 现用网表除外 |
| baseline 精度门控 | [门控对比](precision_register_gating_1108.md) | 大产物已清理 |
| QE 精度门控 | [门控对比](qe_precision_register_gating_1108.md) | 大产物已清理 |

清理逐项清单、保留原因和空间统计：[清理回执](../maintenance/latest_six_artifacts_cleanup_20261110.json)。旧汇总文件名 `latest_six_dp` 是历史名称，不代表当前批次。

## 后续实验记录约定

每次实验新增带日期/版本的 MD 摘要和 JSON/CSV 数据，记录目的、配置、export ID、验证回执、run ID、面积、setup/hold、电气、与基线的差异及限制；更新本页“最新六种 DP”的链接。旧记录不覆盖。清理大产物时更新可用状态和维护回执，保留数值用于长期对比。
