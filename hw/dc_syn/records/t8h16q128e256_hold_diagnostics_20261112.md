# T8H16Q128E256 hold 修复诊断（2026-11-12）

完整 T8H16Q128E256 保留四组基础 T/H/INT8，Q/E 使用全部 16 组。以下两份结果均未通过 hold，不用于功耗。N12 TT/0.7V/85°C、1GHz、ICG、L8/II1；仅综合后、CTS/布局布线前。

| run | area µm² | setup ps | hold ps | hold paths |
|---|---:|---:|---:|---:|
| dc_dp_top_t8h16q128e256_11122104 | 46913.126659 | 0.006914 | -3.713071 | 12 |
| dc_dp_top_t8h16q128e256_11122146 | 46922.600707 | 0.002682 | -3.242522 | 8 |

两份结果的电气及 VT 均通过。第二份为第一份的 hold-only 修复；剩余 8 条路径均为 in_a_datatype[1] 到扩展组 8–15 的 S1 datatype DFF。DFQD1→DFQD2 探针仅改善约 0.03ps 且引入 setup 负值，因此未采用。后续局部分支 DELBD1 identity buffer 探针全局 setup +0.006914ps、hold +1.055464ps，但探针本身不是正式 DC 验收。完整探针证据保存在第二份 run 的 auxiliary/hold_buffer_probe_v2/；原 DDC/netlist 均未改写。

各级 setup、export、层级策略及精确原始目录见同名 JSON；后续正式通过结果须独立发布，不覆盖本诊断。
