# 参数化硬件配置

集中定义见 [Parameters.scala](../chisel_src/config/Parameters.scala) 及 [参数说明](../spec/config/Parameters.md)。参数在生成 RTL 时确定，修改 JSON 即可改变硬件，不改 PE 源码、不依赖隐式环境变量。

| 配置 | 顶层与用途 |
| --- | --- |
| [mn_h16q32e64.json](mn_h16q32e64.json) | 一个全格式 PE+C/D，MN_PE_H16Q32E64 |
| [mn_h0q0e32.json](mn_h0q0e32.json) | 一个半尺寸 E-only PE+C/D，MN_PE_H0Q0E32 |
| [k_h16q64e160.json](k_h16q64e160.json) | Full+Q-only+E64+E32，共享 C/D，K_PE_H16Q64E160 |

JSON 必须包含 schema_version=1、kind（mn/k）、pes。有序 pes 中每项包含 h、q、e、align_width；所有值显式填写，读取器拒绝未知字段和非法组合。MN 的 pes 长度为 1，K 为 1–4。H 为 0/16，Q 为 0/32，E 为 0/32/64；E32 只用于 E-only；至少一个家族非零。同一 K 顶层 align_width 相同，范围 40–64。

```sh
cd hw
mill -i pe.runMain dp.elaborate.Elaborate config configs/mn_h0q0e32.json
export CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin
mill -i pe.runMain dp.elaborate.Generate configs/mn_h0q0e32.json "review E32 structure"
```

本机已存在 `/home/songxy/.cache/mill/download/0.11.8`，可替代 `mill` 命令；firtool 缓存为 `/home/songxy/.cache/llvm-firtool/1.62.0/bin`。路径仅供本机操作，配置 JSON 不保存机器私有路径。

导出目录自动带 top、有效配置 hash、时间和源码 hash；manifest 保留完整参数。可以复制一个小配置文件修改 h/q/e 或 pes 列表做结构探索；每个候选生成后仍需要独立 RTL 验收，不能把生成成功当作数值通过。

这里只记录单阵列/单核内部资源，不记录全芯片核心数、HBM 或芯片级配比。
