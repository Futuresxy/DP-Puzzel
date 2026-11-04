> 功能：定义固定物理移位器的 mux 复用；范围：S3 T/H/Q 共享、E/INT 旁路、S6 幅值对齐及位宽参数；版本：v1.2；修改时间：2026-11-04 19:38:52 +08:00；对应代码：[CModel](../../cmodel/README.md)、[Chisel](../../chisel/README.md)、[Verilog](../../verilog/README.md)（模块文件未建；参数将由 src/chisel/parameter/ 统一传入，目录尚未创建）。

# 参数化共享幅值移位器

状态：用户明确要求固定物理移位器，由输入 mux 选择格式；当前每 lane 四个共享幅值移位器，默认每个 27 位。27 是默认参数结果，非 RTL 内硬编码。

## S3 的物理资源

一个 T1H2Q4E8 lane 同拍最多处理四个 Q 乘积，所以需要四个并行移位器实例。每一个实例同时覆盖 T/H/Q 的互斥用途，不能为 TF32、FP16、BF16、Q 分别实例化一套，再在输出做 mux 并称为共享。主配置 G=4、lane 数=2G，共 `2G×4=32` 个局部共享移位器；这是结构需求，综合后的 cell 数和面积另行测量。

```mermaid
flowchart LR
 P["T/H/Q 乘积与独立 sign"] --> F["各格式静态补零到 W"]
 F --> M["本级 ctrl：输入 mux / 隔离"]
 D["公共 r - 本项指数"] --> C["完整差值检查 / 饱和到 W"]
 M --> S["唯一 W-bit 逻辑右移器实例"]
 C --> S
 S --> N["恢复 sign 为补码"]
 N --> R["S3 叶寄存 / S4 规约"]
```

四个实例采用下列固定路由，索引从 0 开始；其他等价置换必须在导出映射中明确，不能破坏 sign/delta 对应关系。

| 本笔模式 | shifter[0] | shifter[1] | shifter[2] | shifter[3] |
| --- | --- | --- | --- | --- |
| TF32 | T 尾数积 0 | 隔离 | 隔离 | 隔离 |
| FP16/BF16 | H 尾数积 0 | H 尾数积 1 | 隔离 | 隔离 |
| MXFP8/6 | Q 尾数积 0 | Q 尾数积 1 | Q 尾数积 2 | Q 尾数积 3 |
| MXFP4/NVFP4/HiF4 | 宽移位器隔离 | 宽移位器隔离 | 宽移位器隔离 | 宽移位器隔离 |
| INT8 | 宽移位器隔离 | 宽移位器隔离 | 宽移位器隔离 | 宽移位器隔离 |

E 使用 S3 的四个 pair 和及小范围精确移位支路，INT8 使用结构落位支路，两者从叶节点选择 mux 接入同一 S4 树。E 的 HiF4 位移仅 0/1/2，是带保护低零的窄移位；不能额外生成四个全范围宽 barrel shifter。是否让 E 小范围选择也合入同一物理大移位器可另作 PPA 变体，但必须保持逐级数值合同。

## 位宽的唯一配置来源

```text
local_shift_mag_width = 可配置无符号幅值窗口 W，默认 27
product_integer_bits = 2                         // T/H/Q 乘积范围推导
local_align_fraction_bits = W - product_integer_bits
local_signed_width = W + 1
local_shift_control_bits = ceil(log2(W+1))
shifters_per_lane = elements_per_lane_Q
```

`local_shift_mag_width` 是局部移位精度的主配置项；`local_align_fraction_bits` 改为派生量，二者不能作为互相矛盾的独立输入。默认 W=`product_integer_bits+retain_main_fraction_bits=2+25`。当前合法基线要求 F≥25，并满足全部模式的静态补零、E/INT 共享槽以及后级窗口约束；不任意给出未验证的扫描上限。改变 W 会传导到 W_leaf/W_lane/W_group、各模式 F、组 magnitude、anchor 修正、全局窗口合法性和测试参考，不能只改移位器端口。

T/FP16 尾数积为 W22/F20，输入左补的结构低零数是 F-20；BF16 为 F-14；Q 为 F-6。左侧补零/扩宽与低侧补零是不同操作；输入 mux 的每个候选都必须有明确 F，不依靠赋值自动截断。W27 的幅值输出再加 sign 转成 W28 补码。

## 移位单元语义与组合接口

单个逻辑单元为组合算子，计划参数为 width；没有额外 valid 寄存级或 ready。拥有它的 S3/S6 模块负责本周期 ctrl、数据寄存及 valid/last。

| 字段 | 宽度 / 定义 |
| --- | --- |
| in_magnitude | UInt(width)，进入移位器前已经完成格式落位 |
| in_shift | UInt(ceil(log2(width+1)))，0..width；width 表示全部移出 |
| in_active | 1，所属阶段 valid 且本笔格式使用本实例 |
| out_magnitude | UInt(width)，逻辑右移结果；shift≥width 为 0 |

上层 delta 按指数完整范围计算，再 `min(delta,width)` 饱和至端口，不能截断 delta 高位造成模回绕。输入隔离在 mux/算术入口实施：无效/不使用时固定数据与 shift 为零，或者保持已证明不会激活的局部输入；不能仅把输出设零而让所有候选移位器仍切换。

局部移位处理无符号幅值，故右移就是向零截断。负号在移位后恢复；补码树所需的负数变换另属 sign-convert 逻辑，不将负数算术右移当作 RTZ。移出位可供验证统计，首版不作为跨级 sticky 注入最终 RNE。

## S6 的共享规则

S5 所有组已输出统一 sign/magnitude/top-anchor 语义。S6 每个源（G 个组及一个 C）使用固定的 `global_mag_width=global_signed_align_width-1` 位幅值窗口，默认 39；由源类型/布局选择补零与坐标，浮点格式复用同一组物理全局移位器。

当前结构按 N=G+1 个并行对齐源预算，主配置五路；MAX、delta 与移位在 S6 内。INT8/INT32 走可逆结构落位旁路，宽移位器隔离。S3 和 S6 同拍处理不同请求，不能在 II=1 下把两级物理移位器时分复用为同一套。

全局窗口与局部窗口是两个明确参数，分别影响不同截断点；不得隐含绑定为同一宽度。每个源必须满足 pad≥0，精度目标及合法参数检查见 [逐级数值](numeric-layout.md) 和 [出口表](stage-formats.md)。

## 结构与功能验收

后续必须检查输入 mux 后确实仅有四个 W 位局部移位实例/lane，T/H/Q 不并存格式专用的额外宽移位器；分别记录 mux/isolation、shift、sign-convert、寄存器的实际成本。综合优化可以消除恒零路径，不能未经记录复制算术资源。RTL 结构、映射网表和最终资源表分别留证据，源码实例数不等于物理门数。

验证覆盖 T/H/Q 每个活动槽、sign/delta 对应、正负小数 RTZ、delta=0/W-1/W/W+1 及远大于 W 的差值；穿插模式切换与 bubble；参数改变后逐级 F 和 anchor 的数值等价检查。E/INT 旁路要检查宽移位器确实被隔离。当前只有 spec，不运行 RTL 或功耗测试。

## 版本与架构时间线

| 版本 | 修改时间 | 类型 | 修改内容 / 原因 | 来源 |
| --- | --- | --- | --- | --- |
| v1.2 | 2026-11-04 19:38:52 +08:00 | 新建资源合同 | 明确输入 mux 复用固定宽度移位器；W 默认 27 且参数化；区分 S3/S6 与 E/INT 支路及统计归属。 | 用户移位器复用要求 |
