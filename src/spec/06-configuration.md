# 参数与配置合同

状态：首批参数与关系已定义；具体 schema、默认 K 和未决参数待定。下列名称是 spec 的统一符号，不代表已实现 API。

## 集中参数与约束

| 参数/规格常量 | 本轮值或约束 | 性质 |
| --- | --- | --- |
| `group_rows` / `group_cols` | 4 / 4 | 当前广播组结构参数；其他取值待批准 |
| `group_stack_count` | 4 | 竖直组数；当前水平方向只有一组 |
| `k_fp16` | 4、8、16；主配置取 16 | 构建期参数；对应 K4/K8/K16 |
| `base_group_fp16_k` | 4 | 固定基本组基准；T2H4Q8E16 |
| `elements_per_lane[T/H/Q/E]` | 1/2/4/8 | 每组拆两 lane，每 lane T1H2Q4E8 |
| `group_count` | `k_fp16/base_group_fp16_k` | 1/2/4 个并行基本组 |
| `group_sum_growth_bits` | `ceil(log2(group_count))` | 0/1/2 位自然增长 |
| `scale_group_elements` | 16 E 元素 | scale/HiF4 metadata 物理分组参数 |
| `k_mode(mode,k_fp16)` | `(k_fp16/4)*2*(1/2/4/8)`，T/H/Q/E | INT8 与 Q 同并行度；由 lane/formula 派生 |
| `tf32_input_bits` | 32 | 输入容器规格常量，不改变 TF32 数值精度 |
| `retain_main_bits` | ≥25 | 主浮点模式保留目标；计数口径待定 |
| `retain_fp4_bits` | 基准 35 | MXFP4/NVFP4 保留目标；可探索范围待定 |
| `retain_hif4_bits` | 初始目标 37 | HiF4/NVFP4 共享路径推导后确认 |
| `max_dp_pipeline_stages` | 8 | 输入到输出深度上限，不可为时序任意放宽 |
| `latency_by_mode` / `ii_by_mode` | 待定义，L≤8 | 实现结果及协议合同，不得与 K 混淆 |
| `target_frequency_hz` | 1_410_000_000 | 当前时序目标；周期由此派生 |
| `supported_modes` | TF32、FP16、BF16、MXFP8/6/4、NVFP4、HiF4、INT8 | 功能范围；HiF8 排除 |
| `int8_bypass` | 允许评估，选择待定 | 构建期候选；不能当作已存在路径 |

## DP 容量派生

- 基本组为 `T2H4Q8E16`，由两个 `T1H2Q4E8` lane 构成。
- `base_group_count=k_fp16/4`，故 K4/K8/K16 并行使用 1/2/4 组。
- 对模式 T/H/Q/E，`k_mode=base_group_count*2*elements_per_lane[mode]`，lane 项数为 1/2/4/8。K16 得到 T8H16Q32E64。
- E 模式计算组数由 `k_mode(E,k_fp16)/scale_group_elements` 推导；MXFP4/HiF4 scale 槽按相邻组映射，NVFP4 各槽独立，MXFP8/6 32 项块 scale 按两个 E 槽广播。
- K 组和树自然增长 `ceil(log2(base_group_count))` 位；组数为 1 时增长为 0。

## TensorCore 统一派生

- `group_dp_count=group_rows*group_cols`，当前 16。
- `tensorcore_rows=group_rows*group_stack_count`，当前 16。
- `tensorcore_cols=group_cols`，当前 4。
- `tensorcore_dp_count=group_dp_count*group_stack_count`，当前 64。
- `target_period_ns=10^9/target_frequency_hz`。
- 总线宽度从元素容器、模式容量、scale/metadata 布局派生；控制宽度从实际范围推导，单元素/单状态边界明确处理。
- 普通定宽整数乘法的精确结果宽度从两个操作数宽度求和；规约增长根据项数与取值范围推导。浮点对齐、scale、C 合并还需要独立的位宽证明，不能直接套用一个全局公式。

## 禁止魔鬼数值

CModel、Chisel、手写 Verilog 和 testbench 使用相同的有效配置。规格常量集中命名，派生量只从定义计算，不在多个模块重复写 16、64、25、35、37 或流水延迟字面值。

“所有值参数化”包括命名的固定格式常量和有依据的派生表达式，不意味着可以随意改变标准格式编码或把每条局部连线都变为独立自由参数。参数须有单位、作用域、来源、合法性和默认状态；尚未决定的值保持未指定，不能以 0 或旧版值代替。

非法 K、HiF8 模式、低于明确精度下限或超过 8 级的候选不得静默降级。精度计数口径等未闭合项在实施前必须解决，不能仅通过“参数检查”伪装为已验证设计。
