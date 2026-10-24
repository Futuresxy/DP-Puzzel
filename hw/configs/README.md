# 六种PE与K/MN参数配置

唯一默认入口 [Parameters.scala](../chisel_src/config/Parameters.scala)，范围/语义见 [参数spec](../spec/config/Parameters.md)。

```json
{
  "schema_version": 2,
  "top": "k",
  "layout": ["PE_HQE_g4", "PE_E_g2"],
  "alignment": {
    "q_align_width": 28,
    "group_guard_bits": 2,
    "pe_align_width": 40,
    "top_align_width": 40
  }
}
```

profile仅PE_HQE_g4、PE_QE_g4、PE_H_g4、PE_Q_g4、PE_E_g4、PE_E_g2。top=pe/mn时layout只有一项，k为1–4；有序layout决定物理输入槽。q_align_width26..30，group_guard_bits2..4，PE和top窗口38..48且top≥PE。H/Q直接全局路径不用已删除的Q字内/PG局部对齐，仍共享PE输出窗口。

Parameters默认<JSON<CLI，alignment可省略/部分填写，导出记录完整有效配置。未知字段、非整数、非法profile、重复CLI override均拒绝；旧schema1不再接受。加法乘法依自然位宽增长，其他字段不是任意精度旋钮。

```sh
cd hw
mill -i pe.runMain dp.elaborate.Elaborate config configs/pe_q_g4.json --pe-align-width 44 --top-align-width 44
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/k_1_2_6.json "width scan" --q-align-width 30 --group-guard-bits 4 --pe-align-width 48 --top-align-width 48
```

六个pe_*.json对应独立基础PE；k_1_2_6/k_1_2_8/k_1_4_8对应三种异构K布局；mn_q_g4展示专用Q单输出。原full_h16q32e64和full_h48q96e192文件名保留，但内容迁移为schema2的MN单HQE与K三HQE。

导出为参数特化SV，修改配置必须重新生成；各export独立hash和验证。生成/有限smoke不能标记passed或进入PPA。
