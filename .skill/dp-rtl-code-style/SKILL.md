---
name: dp-rtl-code-style
description: >
  DP-Puzzel 项目 Verilog RTL 编码规范与 DFF 基础单元库。当用户编写、修改、审查 Verilog RTL 代码，
  询问编码规范或代码风格，需要例化 DFF 基础单元，创建新的 RTL 模块，或处理以 dp_ 开头的
  Verilog 模块时必须使用此 skill。触发词包括：verilog、RTL、编码规范、DFF、dp_、例化寄存器、
  打拍、代码review、module声明等。
---

# DP-Puzzel 项目 Verilog RTL 编码规范与 DFF 基础单元库

## 适用范围与移植状态

本文件以用户指定的 SN 原始 SKILL.md 为主体移植，保留详细规范、解释、正反例、DFF 选择树、单元列表、模块模板和逐项自检。来源指纹及必要差异见 [移植记录](references/sn-adaptation.md)。本文件是当前完整规范，参考文档仅补充 DP 特有合同。

适用于维护中的 `src/verilog/` 多精度/E 前端和共享模块；冻结的 `systemverilog/` 不迁移，Chisel 默认端口不在此规则范围。纯 Verilog-2005、两空格、UTF-8、LF、100 列目标宽度。当前生产 RTL 仍使用同步高有效 reset，skill 模板未接入生产清单；不得把本次规范移植宣称为 RTL 已完成迁移或 PPA 已通过。

## 仿真收尾

RTL 仿真、复核或失败定位结束后，按根目录 AGENTS.md 和 [运行保留入口](../../scripts/README.md#运行产物保留) 预览清理。各流程滚动保留最近两次已结束且无引用的普通运行；重要结果遵守用户确认及引用保护规则。
归档必要证据，确认没有剩余消费者后释放临时编译中间文件、二进制、生成 C++ 和波形，不因 `--keep-build` 无限积压。
清理使用精确路径清单和 Git/进程检查，不按目录前缀批删，不删除原始源码、在用快照或仍需分析的证据。

## 核心理念

本规范的核心目的是**让寄存器语义和计算结构明确，支持面积、时序和功耗优化**。所有规范服务于这个目标：

- **功能模块禁止手写 `always @(posedge clock)`**，通过 DFF 基础单元明确带/不带复位、带/不带使能的状态保存。DFF 实现内部仍使用行为级时序块并由综合工具映射；封装不能保证某个物理单元或最优 PPA。
- **控制信号用复位寄存器、有效位屏蔽的数据信号用无复位寄存器**。控制需确定初始状态，payload 不必全量复位；计数器若控制请求、地址或循环，仍属于需要初始化的控制状态。
- **多 bit 数据用带使能寄存器**，无效时保持，避免不必要的更新。这提供后端 ICG 优化机会，但须明确启用、配置及验证门控流程；enable 本身不保证 ICG，也不保证上游组合逻辑停止切换。
- **DP 复位保持用户确认的同步低有效 `rst_n`**，优先于使能。所有流水边界以 DFF 实例保存；valid 每拍推进以传播气泡，payload 按有效事件使能，不增加 L8 的流水级数。

---

命名细节同时遵循 [dp-naming-convention](../dp-naming-convention/SKILL.md)：文件、实例、变量的功能词、互联方向、阶段和术语映射以该规范为准。本文保留的通用算术正反例用于解释对应规则，实际新增代码不能据此继续使用 a/e/f 等不明局部名称。

## 一、RTL 编码规范（硬性要求）

### 1. 禁止魔鬼数字

具有设计含义的数字常量必须使用 `parameter`、派生 `localparam` 或 `define 宏定义，禁止在计算/比较/布局中散布魔鬼数字（0、1 等初始化值、声明中的常量定义及示例配置值除外）。数据常量明确宽度；局部计算不必变成全局宏。

```verilog
// ❌ 错误
assign overflow = (count == 4'd15);

// ✅ 正确
localparam [3:0] MAX_COUNT = 4'd15;
assign overflow = (count == MAX_COUNT);
```

### 2. `define 宏只允许在 .vh 头文件中定义

`.v` RTL 源文件中**禁止使用 `` `define`` 定义宏**。所有宏定义必须集中在 `.vh` 头文件中，`.v` 文件通过 `` `include`` 引用。

**为什么要这样？**

- `` `define`` 是**全局命名空间**——不同 `.v` 文件中的同名宏会互相覆盖，调试极其困难
- 把宏集中在 `.vh` 中，所有模块看到同一份定义，保证一致性
- 集中定义减少编译顺序、重定义和配置漂移问题；头文件使用 include guard
- 这是本项目要求，不把风格约束描述成 Verilog 语言禁止在 .v 中定义宏

```verilog
// ❌ 错误 — .v 文件中直接 `define
// 文件: dp_fifo.v
`define DP_FIFO_DEPTH 16
module dp_fifo (...);

// ✅ 正确 — .vh 头文件中定义, .v 文件 include
// 文件: dp_fifo_params.vh
`define DP_FIFO_DEPTH 16

// 文件: dp_fifo.v
`include "dp_fifo_params.vh"
module dp_fifo (...);
```

### 3. 组合逻辑使用 assign

新编写或迁移的功能组合逻辑必须使用 `assign`，通过具名连线、generate、明确的算术/MUX 模块表达结构。**功能层唯一例外是状态机次态逻辑**，可用完整赋值的 `always @(*)`；DFF 原语内部时序块和 TB 不受此组合规则限制。

DP 已有函数和复杂译码/LZD/舍入组合块目前仍存在。迁移时逐模块等价改写并验证，不能仅因这份新规范全库机械替换，不能为凑 assign 形式引入串行优先级链。

```verilog
// ✅ 组合逻辑：用 assign
assign sum = a + b;
assign valid = (state == IDLE) & req;

// ✅ 状态机次态逻辑：允许 always @(*)
always @(*) begin
  next_state = IDLE;
  case (state)
  IDLE: next_state = req ? PROC : IDLE;
  PROC: next_state = done ? IDLE : PROC;
  default: next_state = IDLE;
  endcase
end
```

### 4. 禁止布尔运算符，必须使用按位运算符

Verilog 中 `&&` `||` `!` 是**布尔（逻辑）运算符**，`&` `|` `~` 是**按位（bitwise）运算符**。RTL 编码中**必须使用按位运算符**。

**为什么要区分？**

- `&&` / `||` 将整个操作数解释为真假，输出 1 bit；`&` / `|` 逐位处理，向量结果保留对应位。
- 本项目沿用参考规范的**按位运算风格要求**：条件先显式比较/归约为 1 bit，再用 `&`、`|`、`~` 组合。这样可以在代码中看出归约和门级控制关系。
- 这不是语言正确性禁令。合法的逻辑运算按其语义综合，并不天然导致仿真/综合不一致；多位 `a && b` 不会被正确综合器解释为 `a[0] & b[0]`。迁移必须保留原来的真值/四态语义，禁止直接将多位 `!a` 替换为 `~a`。

**典型错误场景**：

```verilog
// ❌ 错误：用 && 连接两个 8-bit 信号
wire [7:0] a;
wire [7:0] b;
assign flag = a && b;   // 语言合法，但不符合本项目显式归约风格

// ✅ 正确：用 & 做按位与
assign flag = (a != 8'd0) & (b != 8'd0);  // 先归约为 1-bit，再做按位与
// 或者如果要逐位与：
assign and_result = a & b;   // 8-bit 输出，每位独立 AND
```

**条件表达式中的归约**：

```verilog
// ❌ 错误
assign valid = (a == b) && (c == d);   // 布尔 &&

// ✅ 正确
assign valid = (a == b) & (c == d);    // 位与：== 的结果本身就是 1-bit，& 和 && 结果相同但 & 是电路语义
```

**复位信号注意**：

```verilog
// ❌ 错误 — 虽然是手写时序逻辑（本身就禁止），但即使用 DFF 例化外围逻辑也应避免
always @(posedge clock) begin
  if (!rst_n) ...  // 布尔 !
end

// ✅ 正确 — 在组合逻辑/assign 中反相
assign rst_active = ~rst_n;       // 按位取反
assign en_gated   = en & rst_n;  // 按位与
```

**规则表**：

| 运算符 | 类型 | RTL 允许？ | 替代方案 |
|--------|------|-----------|---------|
| `&&` | 布尔与 | ❌ | `&`（单 bit 归约后用 &） |
| `\|\|` | 布尔或 | ❌ | `\|`（单 bit 归约后用 \|） |
| `!` | 布尔非 | ❌ | `~`（按位取反） |
| `&` | 按位与 | ✅ | — |
| `\|` | 按位或 | ✅ | — |
| `~` | 按位取反 | ✅ | — |
| `^` | 按位异或 | ✅ | — |

> 状态机条件也按此风格显式归约后使用 `&` / `|` / `~`。普通 `case` 按四态精确匹配，`==` 与 `===` 的未知值语义不同，不可混用；可综合功能逻辑不用 `casex` 掩盖未知值。TB 和参数合法性检查中的逻辑判断不属于功能控制网风格检查。

### 5. 禁止多维数组直接索引 — 必须显式例化 MUX

动态数组读取/变量选择（例如 `regfile[rd_addr]`、`mem[rd_addr][byte_sel]`）必须显式组织 MUX 模块或 generate 选择树，体现选择路数、数据宽度和预期层级。

**为什么要显式？**

- 便于审查 MUX 规模、选择优先级、广播扇出及关键路径。
- 显式结构仍可能被综合优化，最终层级/面积必须查看报告，不能仅由 RTL 外形保证。
- 常量索引、generate 常量展开、参数化固定切片允许；一维数组声明本身不是违规。真正的存储宏按专用接口合同处理，不强制展开为 DFF+MUX。
- one-hot 选择必须定义零选、多选、越界行为并检查互斥；二进制选择也可使用平衡二选一树，不要求一律转成 one-hot。

```verilog
// ❌ 错误 — 多维索引隐藏了 MUX 结构
wire [63:0] regfile [0:127];   // 128-entry register file
assign rd_data = regfile[rd_addr];  // 综合工具推断 128:1 MUX, 你不知道长什么样

wire [1023:0] bank_mem [0:7][0:255];  // 3D array
assign cell = bank_mem[bank][row];     // 两层索引, MUX 结构完全隐藏

// ✅ 正确 — 显式例化 MUX, 电路结构一目了然
// 128:1 MUX, 7 级 (每级 2:1 树形展开)
wire [63:0] regfile_q [0:127];  // DFF 输出数组
wire [63:0] mux_l0 [0:63];      // 第一级: 128→64

genvar i;
generate
  for (i = 0; i < 64; i = i + 1) begin : gen_mux_l0
    assign mux_l0[i] = rd_addr[0] ? regfile_q[2*i+1] : regfile_q[2*i];
  end
  // ... L1: 64→32, L2: 32→16, ... L6: 2→1
endgenerate

// 也可实例化下文的 dp_lib_bin2onehot + dp_lib_onehot_mux。
// Verilog-2005 的跨模块数据端口用扁平 [N*W-1:0]，不用 unpacked 数组端口。
```

**简化方案**（推荐）：对于较小的一维选择网络，可以使用 generate-for 展开每个 entry 的 "compare + AND + OR" 结构，相当于显式表达 1-hot MUX：

```verilog
// ✅ 显式 1-hot MUX: 每个 entry 一个 AND gate + 全 OR reduce
wire [63:0] rd_data;
genvar i;
wire [63:0] entry_masked [0:127];
generate
  for (i = 0; i < 128; i = i + 1) begin : gen_mux_1hot
    assign entry_masked[i] = (rd_addr == i) ? regfile_q[i] : 64'd0;
  end
endgenerate
// 示意：实际用逐 bit OR 归约或平衡 OR 树连接全部 entry_masked。
// 注: OR 树也可用 generate 逐级展开
```

> **实际工程权衡**：对深度 ≤ 16 的数组，显式 MUX 开销可控。对深度 ≥ 64 的大数组（如 PRF 128×64b），建议在 **module 头部注释中标注 MUX 结构和预期级数**，然后用 generate 模板展开，避免逐个手写。

### 6. 时序逻辑必须例化 DFF 基础单元

**功能模块禁止手写 `always @(posedge clock)`。** 所有普通流水寄存器通过例化本 skill 的 DFF 基础单元保存，DFF 实现内部是例外。存储宏/CDC/ICG 按专用合同，不能强行替换。（DFF 基础单元的 Verilog 代码见 `assets/lib/` 目录。）

```verilog
// ❌ 禁止
always @(posedge clock) begin
  if (!rst_n)  cnt <= 0;
  else         cnt <= cnt + 1;
end

// ✅ 正确：例化 DFF 基础单元（DFF 端口可同行）
dp_lib_DFFRU #(.WIDTH(8))
ff_cnt (.clock(clock), .rst_n(rst_n), .in_d(cnt_next), .out_q(cnt));
```

### 7. 每行一个信号（DFF 例化例外）

信号声明、assign 赋值、普通模块例化的端口连接，都必须每行一个信号。端口每行重复完整方向/类型/位宽；`wire/reg/integer/genvar/parameter/localparam` 不用逗号共享声明。

```verilog
localparam integer GROUP_W = LOCAL_W + 1 + $clog2(`DP_Q_LANES) + $clog2(`DP_LANES);
localparam integer GROUP_MAG_W = GROUP_W - 1;
localparam integer GLOBAL_MAG_W = GLOBAL_W - 1;
localparam integer N = GROUPS + 1;
```

**唯一例外：DFF 基础单元例化**允许将端口放在同一行（因为 DFF 端口固定且简洁，紧凑写法反而可读性更好）。但 DFF 例化时参数 `#(...)` 必须单独一段，实例及端口另起一行；超过目标行宽则展开端口。每个变量声明仍须单独一行。

```verilog
// ❌ 错误：信号声明挤在一行
input wire clock, rst_n, in_en;
// ❌ 错误：普通模块例化端口挤在一行
dp_fifo u_fifo (.clock(clock), .rst_n(rst_n), .in_data(din), .out_data(dout));

// ✅ 正确：信号声明每行一个
input wire clock;
input wire rst_n;
input wire in_en;

// ✅ 正确：普通模块例化每行一个端口
dp_fifo u_fifo (
  .clock   (clock),
  .rst_n (rst_n),
  .in_data(din),
  .out_data(dout)
);

// ✅ 正确：DFF 例化例外 — 端口可放同行，参数单独一行
dp_lib_DFFU #(.WIDTH(8))
ff_data (.clock(clock), .in_d(d), .out_q(q));

// ✅ 同样正确：DFF 例化也可以用展开写法
dp_lib_DFFRE #(.WIDTH(8))
ff_data (
  .clock(clock), .rst_n(rst_n), .in_en(en), .in_d(d), .out_q(q)
);
```

### 8. 寄存器类型选择原则

| 信号类型 | 推荐 DFF | 原因 |
|----------|---------|------|
| 控制信号（FSM 状态、valid/ready、使能等） | DFFRE / DFFRU / DFFSE / DFFSU | 需要确定初始状态 |
| 数据信号（由 valid 屏蔽的 payload 等） | DFFU / DFFE | 无需复位，节省面积 |
| 多 bit 数据通路（≥3 bit） | DFFE（带 en） | 保持无效数据，提供 ICG 优化机会 |

**为什么控制信号用复位、数据信号不用？**
复位树（reset tree）在物理设计中占用可观的布线和 buffer 资源。数据通路寄存器的初始值通常不关心（数据有效由 valid 信号指示），省去复位连接可显著减小面积。但控制信号必须有确定初始状态，否则芯片上电后行为不可预测。

### 9. 命名规范

| 对象 | 规范 | 示例 |
|------|------|------|
| 模块名 | 以 `dp_` 开头，小写；库 DFF 后缀保留 DFFU/DFFE 等类型名 | `dp_fifo_ctrl`, `dp_data_path` |
| 宏定义 | 以 `DP_` 开头，全部大写 | `` `DP_DATA_WIDTH ``, `` `DP_FIFO_DEPTH `` |
| DFF 例化名 | 以 `ff_` 开头 | `ff_state`, `ff_data_0` |
| 信号名 | 小写字母+数字+下划线，表达功能 | `data_valid`, `addr_inc` |
| DP 流水 | 阶段 + d/q；DFF 实例标出两侧阶段 | `sum_s7_q`、`ff_s6_s7_sum` |
| DP 端口 | 时钟 clock、复位 rst_n、输入 in_、输出 out_ | `in_valid`、`out_data` |

### 10. 使能信号与 ICG 优化

多 bit 寄存器（≥3 bit）原则上使用带使能的 DFF（如 `dp_lib_DFFE`）；更窄的有效数据也按相同语义使用使能，不能因位数小而丢失保持要求。后端在正确启用和配置门控流程时可将共享使能提取为 ICG，否则可能映射为反馈 MUX 或带使能单元。检查网表与门控报告，不手写组合门控时钟。

```verilog
// ✅ 32bit 数据打拍，用 DFFE，为后端 ICG 优化提供条件
dp_lib_DFFE #(.WIDTH(32))
ff_data (
  .clock  (clock),
  .in_en   (data_valid),   // 是否生成 ICG 由后端配置和映射验证
  .in_d    (data_in),
  .out_q    (data_out)
);
```

### 11. 代码目录结构

每个功能层级独立组织，共享基础单元只有一份生产实现。保留 DP 已有目录：

```text
src/verilog/
├── common/                 DFF/MUX/编码基础单元（生产迁移时建立）
├── parameter/              dp_defs.vh / dp_functions.vh / 字段布局
├── unpack/                 解包
├── arithmetic/             算术共享模块
├── lane/                   多精度与 E lane
├── group/                  多精度与 E group
├── top/                    dp_top.v / dp_top_e.v
├── files.f                 主实现显式源清单
└── files_e.f               E 实现显式源清单
```

skill 的 `assets/lib/` 为可验证模板；目前没有加入生产 files.f。实施时转入 `src/verilog/common/`，避免同名模块重复编译。旧快照不覆盖。维护对象为 Verilog-2005，不导入参考库中的 SV 数组端口、logic 或隐式语言扩展。

### 12. 禁止 `localparam` 纯别名

如果 `.vh` 中已经用 `` `define `` 定义了某个宏，模块内**禁止**再创建一个同义 `localparam` 别名：

```verilog
// ❌ 错误 — 纯别名，多一层无意义间接引用
`include "dp_xxx_define.vh"
localparam FIFO_DEPTH = `DP_FIFO_DEPTH;

// ✅ 正确 — 直接使用 define
`include "dp_xxx_define.vh"
// 代码中直接写 `DP_FIFO_DEPTH
```

**仅允许**保留有计算公式的派生参数：

```verilog
// ✅ 正确 — 有公式计算的派生参数可以保留
localparam ENTRY_W    = 1 + `DP_IBTB_TAG_W + `DP_IBTB_TARGET_W;
localparam ROW_W      = `DP_IBTB_WAYS * ENTRY_W;
```

### 13. 信号命名必须表达功能，而非来源

信号名要描述**这个信号是什么、做什么**，而非仅仅描述**它从哪来、到哪去**。

```verilog
// ❌ 错误 — 只表达了是 SRAM 的输入输出，没表达含义
wire [239:0] sram_d;    // "SRAM 的 d 端口"  — 不知所云
wire [239:0] sram_q;    // "SRAM 的 q 端口"
wire [9:0]   sram_a;    // "SRAM 的 a 端口"

// ✅ 正确 — 名字表达功能
wire [239:0] sram_wdata;  // SRAM 写入数据
wire [239:0] sram_rdata;  // SRAM 读出数据
wire [9:0]   sram_addr;   // SRAM 读写地址
```

注意：内部变量用功能名，不重复整段模块路径；父模块中的互联线使用 `{driver}_{receiver}_{function}`。可复用模块端口继续使用 `in_{function}` / `out_{function}`，时钟和复位保留 `clock/rst_n`。局部量不用 e/f/a 等不明简称，区分 exponent_field、fraction_field、fractional_bits 和 magnitude；详见命名 skill。

### 14. 模块 interface 禁止 pack 独立信号为单 bus

核心原则是**不能为了 pack 而引入魔鬼数字**。判断标准：pack 之后，下游使用方是否需要写裸 slice（如 `[49:2]`）才能提取信号？

**❌ 不可接受**：pack 成对外 output port，下游被迫写 slice 提取：
```verilog
output wire [64:0] b2_b3_mbtb_pred_o;
// 下游调用者被迫写魔鬼数字：
assign hit    = b3_mbtb_pred[0];
assign target = b3_mbtb_pred[49:2];
```

**✅ 可以接受**：模块内部 pipeline DFF 中临时 pack 以节省例化行数，但下游代码立即解包为命名 wire，且解包位置紧邻 DFF 例化：
```verilog
// 内部 pipeline: pack 进一条 DFF，紧跟着解包为命名 wire
wire [205:0] b2_b3_d;
wire [205:0] b2_b3_q;
assign b2_b3_d = {b2_pc, b2_tid, b2_valid,
                  mbtb_hit, mbtb_taken, mbtb_target, mbtb_brtype, ...};
dp_lib_DFFU #(.WIDTH(206))
ff_b2_b3 (.clock(clock), .in_d(b2_b3_d), .out_q(b2_b3_q));
// 立刻解包 — 下游代码只用命名 wire，无魔鬼数字
assign {b3_pc, b3_tid, b3_valid,
    b3_mbtb_hit, b3_mbtb_taken, b3_mbtb_target, b3_mbtb_brtype, ...} = b2_b3_q;
```

**✅ 也可以接受**：多个同类信号做结构化 pack，且访问方式自描述（如输入总线中包含多个相同结构的 lane，用 `[ENTRY_W-1:0]` 而非裸数字 slice）。

**判断标准一句话**：下游代码中如果出现 `[49:2]`、`[52:50]` 这类无注释的裸 slice → 不可接受。如果解包后下游只用命名 wire → 可以接受。

### 15. 打包结构必须用 `define 定义 bit-field 布局

当固定的共享信号包含多个字段（如 token 中的 sign/anchor/magnitude），必须在 `.vh` 用 `` `define `` 定义字段位置。对于随 K/LOCAL_W/GLOBAL_W 变化的布局，用具名派生 `localparam` 计算宽度/偏移，不能用固定宏冻结参数化布局。模块代码中**禁止**出现裸数字 slice。

```verilog
// ❌ 错误 — 裸 slice 无文档，修改 entry 格式时需全局搜索替换
assign way_valid[0] = way_data[0][59];
assign way_tag[0]   = way_data[0][58:48];
assign way_target[0] = way_data[0][47:0];

// ✅ 正确 — define 定义所有 bit 位置
// 在 .vh 中：
`define DP_IBTB_ENTRY_W          60
`define DP_IBTB_VALID_BIT        59
`define DP_IBTB_TAG_MSB          58
`define DP_IBTB_TAG_LSB          48
`define DP_IBTB_TARGET_MSB       47
`define DP_IBTB_TARGET_LSB       0

// 在 .v 中：
assign way_valid[0]  = way_data[0][`DP_IBTB_VALID_BIT];
assign way_tag[0]    = way_data[0][`DP_IBTB_TAG_MSB:`DP_IBTB_TAG_LSB];
assign way_target[0] = way_data[0][`DP_IBTB_TARGET_MSB:`DP_IBTB_TARGET_LSB];
```

**要求**：每个包含多字段的固定共享结构，在 `.vh` 中必须有对应的 entry layout define 块，并按如下顺序组织：

```
// {结构名} entry layout ({总宽度}b):  field1(w1) + field2(w2) + ...
`define DP_{STRUCT}_ENTRY_W     {总宽度}
`define DP_{STRUCT}_FIELD1_MSB  {最高位}
`define DP_{STRUCT}_FIELD1_LSB  {最低位}
`define DP_{STRUCT}_FIELD2_MSB  {最高位}
`define DP_{STRUCT}_FIELD2_LSB  {最低位}
...
```

### 16. 写完后强制自检

**每次编写或修改 RTL 代码后，必须逐条自检以下 15 项，并在回复中输出自检结果。** 这是硬性要求，不允许跳过。

自检输出格式（必须逐条标注通过/不通过）：

```
## RTL 自检报告

| # | 检查项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | 无魔鬼数字 | ✅ / ❌ | ... |
| 2 | `define 只在.vh中定义 | ✅ / ❌ | ... |
| 3 | 组合逻辑用 assign | ✅ / ❌ | ... |
| 4 | 禁止布尔运算符 `&&` `\|\|` `!` | ✅ / ❌ | ... |
| 5 | 禁止多维数组直接索引 | ✅ / ❌ | ... |
| 6 | 时序逻辑例化 DFF | ✅ / ❌ | ... |
| 7 | 每行一个信号（DFF例化除外） | ✅ / ❌ | ... |
| 8 | 寄存器类型选择正确 | ✅ / ❌ | ... |
| 9 | 命名规范 | ✅ / ❌ | ... |
| 10 | 多bit数据用带en的DFF | ✅ / ❌ | ... |
| 11 | 目录结构正确 | ✅ / ❌ | ... |
| 12 | 无 localparam 纯别名 | ✅ / ❌ | ... |
| 13 | 信号名表达功能（非来源） | ✅ / ❌ | ... |
| 14 | pack 后无裸 slice 解包 | ✅ / ❌ | ... |
| 15 | bit-field slice 用 define | ✅ / ❌ | ... |

总结：15/15 通过 或 ❌ 项需修复：xxx
```

本次修改涉及的项目必须修复后重新自检；不涉及的项目写 N/A 并说明，未运行的检查写“未检查”，不能虚报全部通过。既有未迁移模块注明范围，不借风格审查擅自改动用户代码。另检查 DP 的同步复位、valid/payload 对齐、参数化 S/I/F、L8/II=1 和验证回执。

---

## 二、基础单元库

本 skill 的基础单元模板位于 `assets/lib/` 目录，分为 **DFF 时序单元** 和 **组合逻辑单元** 两类。

> **工程说明**：六种 DFF wrapper 共用 `dp_dff_en.v` / `dp_dff_sync_reset.v` 两个行为级实现，编译时包含对应依赖；任意控制复位常量可直接参数化后者。模板目前未接入生产 RTL。后续在 `src/verilog/common/` 建立唯一生产实现，并更新源清单和验证；不要同时编译模板与同名生产模块。基础单元是行为级 RTL，不是 PDK 单元。

### DFF 选择决策树

```
需要寄存器？
├── 是控制信号？(FSM状态/valid/ready/handshake)
│   ├── 需要enable？ → dp_lib_DFFRE（复位）/ dp_lib_DFFSE（置位）
│   └── 不需要enable → dp_lib_DFFRU（复位）/ dp_lib_DFFSU（置位）
│
├── 是数据信号？(valid 屏蔽的 payload/data_path)
│   ├── 需要enable且≥3bit？ → dp_lib_DFFE（使能保持/ICG候选）
│   ├── 需要enable但<3bit？ → dp_lib_DFFE（仍保留使能语义）
│   └── 不需要enable → dp_lib_DFFU
│
└── 纯打拍延迟（无功能逻辑）
    ├── 带使能条件 → dp_lib_DFFE
    └── 每拍都有效 → dp_lib_DFFU
```

### 单元列表

#### dp_lib_DFFU — 基础 D 触发器（无复位、无使能）

- **文件**: `assets/lib/dp_lib_DFFU.v`
- **用途**: 纯数据打拍，不需要复位和使能的场景
- **参数**: `WIDTH = 8`
- **端口**: `clock`, `in_d[WIDTH-1:0]`, `out_q[WIDTH-1:0]`

```verilog
// 例化模板（DFF 端口可同行，参数单独一行）
dp_lib_DFFU #(.WIDTH(<width>))
ff_<name> (.clock(<clock>), .in_d(<data_in>), .out_q(<data_out>));
```

#### dp_lib_DFFE — 带使能 D 触发器（无复位）

- **文件**: `assets/lib/dp_lib_DFFE.v`
- **用途**: 数据通路打拍，≥3bit 推荐使用（使能保持/ICG 候选）
- **参数**: `WIDTH = 8`
- **端口**: `clock`, `in_en`, `in_d[WIDTH-1:0]`, `out_q[WIDTH-1:0]`

```verilog
// 例化模板（DFF 端口可同行，参数单独一行）
dp_lib_DFFE #(.WIDTH(<width>))
ff_<name> (.clock(<clock>), .in_en(<enable>), .in_d(<data_in>), .out_q(<data_out>));
```

#### dp_lib_DFFRU — 带同步复位 D 触发器（复位值 = 0）

- **文件**: `assets/lib/dp_lib_DFFRU.v`
- **用途**: 控制信号打拍，需要复位到 0
- **参数**: `WIDTH = 8`
- **端口**: `clock`, `rst_n`, `in_d[WIDTH-1:0]`, `out_q[WIDTH-1:0]`

```verilog
// 例化模板（DFF 端口可同行，参数单独一行）
dp_lib_DFFRU #(.WIDTH(<width>))
ff_<name> (.clock(<clock>), .rst_n(<reset_n>), .in_d(<data_in>), .out_q(<data_out>));
```

#### dp_lib_DFFRE — 带同步复位 + 使能 D 触发器（复位值 = 0）

- **文件**: `assets/lib/dp_lib_DFFRE.v`
- **用途**: 控制信号打拍，需要复位且带使能条件
- **参数**: `WIDTH = 8`
- **端口**: `clock`, `rst_n`, `in_en`, `in_d[WIDTH-1:0]`, `out_q[WIDTH-1:0]`

```verilog
// 例化模板（DFF 端口可同行，参数单独一行）
dp_lib_DFFRE #(.WIDTH(<width>))
ff_<name> (.clock(<clock>), .rst_n(<reset_n>), .in_en(<enable>), .in_d(<data_in>), .out_q(<data_out>));
```

#### dp_lib_DFFSU — 带同步置位 D 触发器（置位值 = 全 1）

- **文件**: `assets/lib/dp_lib_DFFSU.v`
- **用途**: 控制信号打拍，需要复位到全 1（仅用于合同明确需要全 1 的状态；one-hot 状态不能默认全 1）
- **参数**: `WIDTH = 8`
- **端口**: `clock`, `rst_n`, `in_d[WIDTH-1:0]`, `out_q[WIDTH-1:0]`

```verilog
// 例化模板（DFF 端口可同行，参数单独一行）
dp_lib_DFFSU #(.WIDTH(<width>))
ff_<name> (.clock(<clock>), .rst_n(<set_n>), .in_d(<data_in>), .out_q(<data_out>));
```

#### dp_lib_DFFSE — 带同步置位 + 使能 D 触发器（置位值 = 全 1）

- **文件**: `assets/lib/dp_lib_DFFSE.v`
- **用途**: 控制信号打拍，需要置位且带使能条件
- **参数**: `WIDTH = 8`
- **端口**: `clock`, `rst_n`, `in_en`, `in_d[WIDTH-1:0]`, `out_q[WIDTH-1:0]`

```verilog
// 例化模板（DFF 端口可同行，参数单独一行）
dp_lib_DFFSE #(.WIDTH(<width>))
ff_<name> (.clock(<clock>), .rst_n(<set_n>), .in_en(<enable>), .in_d(<data_in>), .out_q(<data_out>));
```

---

### 组合逻辑单元

以下为组合基础模块，用于显式表达动态选择和编码。MUX 的零选输出为零，多选会按位 OR，调用方必须保证 one-hot-or-zero；编码器的零输入输出零，需另外传递 valid；多热编码是非法请求，不表示优先级。正整数宽度和路数由配置/导出检查，超出编码空间的配置必须拒绝。

#### dp_lib_onehot_mux — One-Hot 多路选择器

- **文件**: `assets/lib/dp_lib_onehot_mux.v`
- **用途**: 将 `N` 路输入按 1-hot 选择信号选出一路输出。**替代 `array[idx]` 隐式 MUX**
- **参数**: `N` = 输入路数, `W` = 数据宽度
- **端口**: `out_data[W-1:0]`、`in_select[N-1:0]`、`in_data[N*W-1:0]`（第 i 路占 `[i*W +: W]`）

```verilog
// 例化模板: 128-entry 寄存器文件读口, 64-bit
dp_lib_onehot_mux #(.N(128), .W(64)) u_rf_rd (
  .in_select(rd_onehot),
  .in_data(regfile_flat_q),
  .out_data(rd_data)
);
```

#### dp_lib_bin2onehot — 二进制 → 1-hot 译码器

- **文件**: `assets/lib/dp_lib_bin2onehot.v`
- **用途**: 将二进制地址译码为 1-hot 选择信号。常用于寄存器文件写使能、仲裁器选择
- **参数**: `BIN_W` = 二进制位宽, `ONEHOT_W` = 1-hot 位宽（1 到 2^BIN_W，支持非二次幂路数）
- **端口**: `out_onehot[ONEHOT_W-1:0]`、`in_binary[BIN_W-1:0]`

```verilog
// 例化模板: 7-bit 地址 → 128-bit 1-hot
dp_lib_bin2onehot #(.BIN_W(7), .ONEHOT_W(128)) u_dec (
  .in_binary(wr_addr),
  .out_onehot(wr_onehot)
);
```

#### dp_lib_onehot2bin — 1-hot → 二进制编码器

- **文件**: `assets/lib/dp_lib_onehot2bin.v`
- **用途**: 将 1-hot 信号编码为二进制索引。常用于已经互斥的仲裁器 grant → 索引，不包含优先级决策
- **参数**: `BIN_W` = 二进制位宽, `ONEHOT_W` = 1-hot 位宽
- **端口**: `out_binary[BIN_W-1:0]`、`in_onehot[ONEHOT_W-1:0]`

```verilog
// 例化模板: 128-bit 1-hot → 7-bit 二进制索引
dp_lib_onehot2bin #(.BIN_W(7), .ONEHOT_W(128)) u_enc (
  .in_onehot(gnt_onehot),
  .out_binary(gnt_idx)
);
```

### 组合逻辑单元选择指南

```
需要选择电路？
├── 多选一（MUX）
│   ├── 选择信号已是 1-hot → dp_lib_onehot_mux
│   └── 选择信号是二进制 → dp_lib_bin2onehot + dp_lib_onehot_mux
│
├── 需要译码（二进制→1-hot）→ dp_lib_bin2onehot
│   （写使能生成、bank选择、per-entry控制）
│
├── 需要编码（1-hot→二进制）→ dp_lib_onehot2bin
│   （仲裁结果编码、优先级编码）
│
└── 复杂优先级 → 专用优先级选择模块 + dp_lib_onehot2bin（优先级模块按需求实现，模板库未提供）
    （先做优先级屏蔽，再编码）
```

> **设计原则**：动态数组选择必须显式组织；可用 `dp_lib_bin2onehot` + `dp_lib_onehot_mux` 或平衡二选一树。标明规模和预期层级，综合后再验证真实关键路径。

---

## 三、典型代码示例

本节及前面的正反例中，带 `...` / `<width>` 等标记的是结构片段，需替换后使用；示例 4 与 assets 中同名完整模块一致，已实际编译仿真。

### 示例 1：带使能的数据通路打拍（数据信号）

```verilog
// 32bit 数据寄存器，带使能，无复位
// 无效拍保持；是否映射 ICG 由后端流程验证
dp_lib_DFFE #(.WIDTH(32))
ff_data_out (.clock(clock), .in_en(data_valid), .in_d(data_in), .out_q(data_out));
```

### 示例 2：FSM 状态寄存器（控制信号）

```verilog
// FSM 状态机，需要复位到 IDLE(=0)
localparam [2:0] IDLE = 3'd0;
localparam [2:0] PROC = 3'd1;
localparam [2:0] DONE = 3'd2;

assign state_next = ...;  // 组合逻辑生成次态

dp_lib_DFFRU #(.WIDTH(3))
ff_state (.clock(clock), .rst_n(rst_n), .in_d(state_next), .out_q(state));
```

### 示例 3：带使能条件更新的计数器

```verilog
parameter integer CNT_WIDTH = 8;

localparam [CNT_WIDTH-1:0] CNT_ONE = {{(CNT_WIDTH-1){1'b0}}, 1'b1};
assign cnt_next = cnt + CNT_ONE;

dp_lib_DFFRE #(.WIDTH(CNT_WIDTH))
ff_cnt (.clock(clock), .rst_n(rst_n), .in_en(inc_en), .in_d(cnt_next), .out_q(cnt));
```

### 示例 4：完整模块模板

```verilog
// Structural example only, not an implementation of the DP S3 arithmetic.
// Store an opaque magnitude and its separate sign at the S2 -> S3 boundary.
// Magnitude S=0, I+F=DATA_W; the caller defines the binary-point coordinate.
// One edge of latency, II=1, no backpressure; reset cancels valid synchronously.
module dp_pipeline_boundary_example #(
  parameter integer DATA_W = 28
) (
  input wire clock,
  input wire rst_n,
  input wire in_valid,
  input wire [DATA_W-1:0] in_magnitude,
  input wire in_sign,
  output wire out_valid,
  output wire [DATA_W-1:0] out_magnitude,
  output wire out_sign
);

  localparam integer SIGN_W = 1;
  localparam integer PAYLOAD_W = SIGN_W + DATA_W;

  wire valid_s3_d;
  wire valid_s3_q;
  wire payload_s3_en;
  wire [PAYLOAD_W-1:0] payload_s3_d;
  wire [PAYLOAD_W-1:0] payload_s3_q;
  wire [DATA_W-1:0] magnitude_s3_q;
  wire sign_s3_q;

  assign valid_s3_d = in_valid;
  assign payload_s3_en = rst_n & in_valid;
  assign payload_s3_d = {in_sign, in_magnitude};

  // S2 -> S3 control: advance every edge, including bubbles; reset to invalid.
  dp_lib_DFFRU #(
    .WIDTH(1)
  ) ff_s2_s3_valid (
    .clock(clock),
    .rst_n(rst_n),
    .in_d (valid_s3_d),
    .out_q(valid_s3_q)
  );

  // S2 -> S3 payload: save only a valid item, hold during reset and bubbles.
  dp_lib_DFFE #(
    .WIDTH(PAYLOAD_W)
  ) ff_s2_s3_payload (
    .clock(clock),
    .in_en(payload_s3_en),
    .in_d (payload_s3_d),
    .out_q(payload_s3_q)
  );
  assign {sign_s3_q, magnitude_s3_q} = payload_s3_q;

  assign out_valid = valid_s3_q;
  assign out_magnitude = magnitude_s3_q;
  assign out_sign = sign_s3_q;

endmodule
```

---

## 四、代码审查指南

### 审查他人代码时

逐项对照规范检查，同时关注以下常见违规模式：

| # | 常见违规 | 识别方法 |
|---|---------|---------|
| 1 | 裸数字出现在比较/赋值中 | 搜索常量后区分命名定义与散布的设计数值 |
| 2 | `.v` 文件中使用 `` `define`` | 搜索 `` `define`` 出现在 `.v` 文件中 — 应移到 `.vh` |
| 3 | 手写 `always @(posedge clock)` | 搜索功能模块中的 `always @(posedge`，DFF 原语除外 |
| 4 | 使用布尔运算符 `&&` `\|\|` `!` | 搜索 `&&` `\|\|` `! ` — 先验证宽度/真值，再显式归约并改为按位组合 |
| 5 | 多维数组直接索引 `arr[a][b]` | 区分静态索引与动态读取；动态读取改为显式选择结构 |
| 6 | 多个信号挤在一行（DFF例化除外） | 搜索逗号分隔的 input/output/wire 声明，以及非DFF模块例化的逗号端口连接 |
| 7 | 数据信号用了带复位的 DFF | 检查数据通路 DFF 例化类型 |
| 8 | 模块名未用 dp_ 前缀 | 搜索 `module ` |
| 9 | 多 bit 数据未用 en | 检查 payload DFF 是否连接 .in_en，或有每拍更新的合同依据 |
| 10 | `localparam` 纯别名 | 搜索 `localparam \w+ = \`  → 删除别名，直接用 define |
| 11 | 信号名只描述来源 | 检查 `sram_d`、`tag_q` 类命名 → 应改为 `sram_wdata`、`pipelined_tag` |
| 12 | 独立信号 pack 后下游裸 slice | 搜索 `\[\d+:\d+\]` 在解包逻辑中 → 应拆为独立 port 或在 pack 处紧邻解包为命名 wire |
| 13 | 裸数字 bit slice | 搜索 `\[\d+:\d+\]` 在 way_data/sram_rdata 等结构访问中 → 应改用 define |

### 审查输出格式

使用与自检相同的表格格式（参见“写完后强制自检”），逐项标注 ✅/❌ 并给出具体行号和修复建议。


## 五、DP 特有合同与迁移验证

- 头文件、派生位宽、signed/unsigned、移位/截断/舍入必须显式；各计算节点及树/乘法器输入输出按精度逐行列 S/I/F 表，SM 符号单独传递，TC 与 SM 不能混用。见 [DP 数值细则](references/coding-style.md)。
- 默认 K16/LOCAL_W28/GLOBAL_W40，容量 T8H16Q32E64；E64 前端共用后端。实际参数支持范围以 spec 为准；宽度随参数推导，非法配置拒绝，不能将 40-bit 总宽等同于 40-bit 数值精度。
- 功能层 DFF 实例明确保存边界；每个阶段 valid 每拍更新，payload 使能为 `rst_n & valid_previous`，气泡不重复输出，复位取消在途。详见 [寄存器合同](references/registers.md)。
- 文档/模板移植不修改生产 RTL；迁移时同步主/E 接口、TB、断点层级、导出 manifest 和 DC/功耗入口，分别完整回归，保持 L8/II=1。禁止改旧快照或借旧 PPA 结论证明新版本。
- Verible 只处理排版及部分风格，不能自动证明本规范全通过。保留 Verilog-2005，不为 lint 引入 SV；lint、数值/周期测试和 STA 分别给出证据。
- 开发在当前 feat/dp-verilog-v14；保留用户改动，遵从 AGENTS.md 的提交、分支、清理和工艺保密规则。
