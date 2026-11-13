> 功能：Q8 专用 group；范围：两条 Q4 lane 的 S1–S5 与公共 token 输出；版本：v1.10；修改时间：2026-11-12 18:50:00 +0800；对应代码：src/verilog/group/dp_group_q.v、src/verilog/lane/dp_lane_q.v、src/cmodel/lib/group/group_q.cpp；Chisel 未实现。

# Q8 专用 group

`dp_group_q` 含两条 [Q4 lane](../lane/dp_lane_q.md)，A/B 各64 bit。只支持四种 MXFP8/6，scale 固定 E8M0，每侧一个字节。父层负责合法 scale datatype 与跨组块广播；Q group 无 E scale 尾数乘法，无 HiF 元数据端口。输出字段、位宽与输出时刻兼容当前 v1.9 group。

S1 保存 A/B scale 无偏有符号指数 `raw−127`（S8）及 scale NaN（编码255）；S2 合并为 S9，并捕获两 lane 的有限非零公共 U6 MAX。S3 提前计算 `A_raw = group_max + scale_exponent_sum + M−1−(LOCAL_W−2)−30`，S4 只延迟该坐标。scale 显著数恒为1，不需要系数积寄存器或 scale 幅值乘法。

S5 两个 S4 lane 的 S31 和用一层加法合并到 S32，符号分离得到 U31 幅值。零结果仅在两 lane 原始乘积全负时保留负号。special 按 lane 分类合并并纳入 scale NaN；特殊/零值不参与数值指数 MAX，但 special 仍单独传递。

| S5 输出 | 默认宽度 | 语义 |
| --- | --- | --- |
| `out_valid` | 1 | 输入接受后第5个寄存边界，II=1 |
| `out_negative` | 1 | 包含负零的独立符号 |
| `out_magnitude` | U31 | 未规格化幅值；M=LOCAL_W+3 |
| `out_anchor` | S10 | A_raw，对应幅值最高物理位的指数坐标 |
| `out_compare_exp` | S10 | 有限非零时 A_raw−LZD_M；其余置安全值0 |
| `out_z` | U5 | 兼容观察 `out_anchor−out_compare_exp`；不是后端重算指数的输入 |
| `out_special` | 4 | NaN、invalid、正/负Inf |

有限数值不变量：`value=(-1)^negative × magnitude × 2^(A_raw−(M−1))`。默认Q组的独立符号与U31幅值对应 I5F26。S5 只检测 LZD，不移动幅值；S6 在唯一全局 Emax 下对每个 token 进行一次 RTZ 对齐。

`LOCAL_W≥27`，默认28；`GROUP_W=LOCAL_W+4`，`MAG_W=GROUP_W−1`。组内固定两 lane，S2 MAX 不增加寄存级；S5 输出与基础 group 同拍。同步低有效复位清空 valid，所有 payload 只在合法 Q 请求占据对应级时更新。父层非参与模式不向本组发请求；后端仍须分别屏蔽 MAX、special 和全负零贡献，不能只把幅值清零。
