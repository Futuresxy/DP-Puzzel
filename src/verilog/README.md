# 多精度 DP · 手写 RTL

实现单个 `scaled_dot(A,B)+C` 点积单元，遵循 **spec v1.5 / 实现映射 v1.5.1**。默认 T8H16Q32E64、八级流水、II=1，逐请求切换格式；没有跨请求累加状态或计算阵列。

| 实现 | 编译清单 | 顶层 |
| --- | --- | --- |
| **Verilog-2005，主要交付** | [files.f](files.f) | [dp_top.v](top/dp_top.v) |
| SystemVerilog，对照实现 | [systemverilog/files.f](systemverilog/files.f) | [dp_top.sv](systemverilog/top/dp_top.sv) |

两套源码独立可综合，module 名相同，必须分开编译。Verilog 版使用 `wire/reg`、显式端口、具名 `generate`、头文件常量及 Verilog 函数，不使用 package、struct、logic、always_ff、always_comb 或 SV cast。SystemVerilog 版保留 packed token 与 package，不能当作 Chisel 生成 RTL。两版没有运行时软件计算/DPI、real 运算或黄金结果查表。

## 参数与层级

| 参数 | 默认值 | 合同 |
| --- | --- | --- |
| `K_FP16` | 16 | 4 / 8 / 16；基本组数 `G=K_FP16/4` |
| `LOCAL_W` | 28 | S3 幅值窗口，至少 27；T/H/Q 小数位为 `LOCAL_W−2` |
| `GLOBAL_W` | 40 | S6 补码叶宽，幅值移位器为 `GLOBAL_W−1`；要求 `GLOBAL_W >= max(LOCAL_W+4, 33)` |

`GROUPS` 等派生参数不可独立改变。组宽、树深、自然增长位、LZD 计数与 anchor 宽度从格式常量、项数和窗口推导。固定编码字段与共享粒度集中在 [dp_defs.vh](parameter/dp_defs.vh)，数值坐标公式在 [dp_functions.vh](parameter/dp_functions.vh)。这些是架构常量，不是允许任意改变输入编码的旋钮。

```text
dp_top                         单个 DP，C 传递/解包及 S6–S8
├── g_group[g].group_unit       T2H4Q8E16，scale 与共同 MAX，S5
│   └── g_lane[l].lane          T1H2Q4E8，S1–S4
│       ├── operand_unpack_a/b 每侧两份 E10/M16/S4 物理寄存布局
│       ├── mantissa_mul_bank   两套 HH/HL/LH/LL
│       ├── exponent_add       两套 8-bit/5-bit 指数加法器
│       ├── g_align[j]          四个 LOCAL_W 固定移位器
│       └── lane_sop_tree       平衡有符号规约
├── c_unpack                    S5 独立一份
├── global_alignment            G+1 个双向移位器
├── final_sop_tree               G+1 项，自然增长
└── fp32_output                 RNE、渐进下溢与 FP32 打包
```

每个 module 单独同名文件。组合模块不暗加寄存器；S1 寄存器由 lane 内 `dp_lane_unpack` 持有，其余流水由 lane、group、top 三层持有。同步高有效 `reset` 清除有效控制并取消在途请求；数据寄存器以有效使能保持，不进行全数据复位。握手、阶段映射、源文件和统计归属见 [RTL 实现合同](../spec/dp/implementation/verilog.md)。

尾数定点格式注释使用对齐表格，每行一种或一类精度，独立列出 S、I、F。表前说明 SM 独立符号或 TC 二补码，以及 P、L 等参数的定义。乘法器输入和输出分别列出各自的 S、I、F。解包和尾数乘法表列有效 coefficient 的格式；通用槽的高位零扩展不增加 F，树和级间输出表按数值通路宽度列示。

## 纯 Verilog 排版

`*.v` 使用两空格缩进、LF 换行和 100 列目标行宽。共享一条端口声明的信号同排，例如 ``input wire [K_FP16*`DP_HALF_W-1:0] in_a,in_b,``。对含这类声明的端口列表，用 `verilog_format: off/on` 保留分组，其余代码由 Verible 格式化。

从仓库根目录使用 Verible `v0.0-4298-g085eef05` 批量整理已跟踪的 `*.v` 文件。

```sh
git ls-files -z -- ':(glob)src/verilog/**/*.v' |
  xargs -0 -r verible-verilog-format --inplace --failsafe_success=false \
    --indentation_spaces=2 --wrap_spaces=2 --column_limit=100 --try_wrap_long_lines \
    --formal_parameters_indentation=indent --port_declarations_indentation=indent \
    --named_parameter_indentation=indent --named_port_indentation=indent
```

## 验证

先按 [CModel 说明](../cmodel/README.md) 构建参考模型，然后从仓库根目录运行：

```sh
# 默认：Verilator + 同一份纯 Verilog testbench，同时比较两版
python3 test/run_verilog.py --phase all

# 只测主要交付；Verilator 可通过参数或 VERILATOR 环境变量指定
python3 test/run_verilog.py --implementation verilog --verilator /path/to/verilator

# 独立四态仿真及严格 Verilog-2005 语法检查
python3 test/run_verilog.py --simulator iverilog --implementation verilog
```

[dp_tb.v](../../test/rtl_tb/dp_tb.v) 直接读取共用 `DP_INPUTS_V1`，逐笔检查 D/type/last、L8、原子 ready、气泡、复位及非法元组拒收。它输出 `results.txt` 和 `PASS` 统计；参数回归还输出 S1–S7 断点，与 CModel trace 比较。脚本另用独立调度队列核对输出顺序，并比较两版结果文件指纹。

每次验证先将源代码冻结到 `hw/rtl/DP_<implementation>_<fingerprint>/`，保存 portable `files.f`、源/快照 SHA、RTL_ID、README、参数与验证范围。运行日志、构建产物、逐笔输出和断点在 `test/runs/verilog/`，不提交。精简证据见 [RTL 报告](../../test/results/verilog-v1.4.md)。

RTL 单独执行 `-Wall` lint，位宽、锁存器、组合环类警告不豁免。非功能豁免仅限 `UNUSEDSIGNAL`（显式冗余位/观察点）、`UNUSEDPARAM`（共用格式表）、`VARHIDDEN`（Verilog 共享函数头在各模块独立展开）。TB 编译另外允许 integer 文件读取宽度、timescale 和初始化调度告警；这不替代前述 RTL lint。

## 当前边界

只实现 L8；CModel 的 L9 备用探索未在这两套 RTL 中开放。未实现 Chisel、DP-Group、TensorCore/Cube、专用 Q/E/QE 扩展或独立对齐方案。历史 27/40 的 N12 TT 在 1.41 GHz setup 未达标；逐级证据与 1GHz 后续测量见 [时序分析](../../hw/dc_syn/records/dp_n12_timing_20261105.md)。尚无布局布线或真实活动功耗。

DC 接入使用 [统一门禁与流程](../../hw/dc_syn/README.md)。Verilog 的运行时 `lane_fraction` 已改为等价常量选择以兼容 DC；新快照重新完整回归，不继承旧 snapshot 的通过状态。
