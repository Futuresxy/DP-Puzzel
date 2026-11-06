# 多精度 DP · 手写 RTL

实现单个 `scaled_dot(A,B)+C` 点积单元，遵循 **spec v1.5 / 实现映射 v1.5.1**。默认 T8H16Q32E64、八级流水、II=1，逐请求切换格式；没有跨请求累加状态或计算阵列。

| 实现 | 编译清单 | 顶层 |
| --- | --- | --- |
| **Verilog-2005，主要交付** | [files.f](files.f) | [dp_top.v](top/dp_top.v) |
| **E-only Verilog-2005** | [files_e.f](files_e.f) | [dp_top_e.v](top/dp_top_e.v) |
| SystemVerilog，冻结的历史参考 | [systemverilog/files.f](systemverilog/files.f) | [dp_top.sv](systemverilog/top/dp_top.sv) |

当前维护纯 Verilog。SystemVerilog 仅保留当前 T8H16Q32E64 历史源码，冻结来源和边界见 [历史参考说明](systemverilog/README.md)；后续新功能和 E 专用设计不再同步 SV。两套源码的 module 名相同，历史重放必须分开编译。Verilog 版使用 `wire/reg`、显式端口、具名 `generate`、头文件常量及 Verilog 函数，不使用 package、struct、logic、always_ff、always_comb 或 SV cast。SystemVerilog 版保留 packed token 与 package，不能当作 Chisel 生成 RTL。两版没有运行时软件计算/DPI、real 运算或黄金结果查表。

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

每个 module 单独同名文件。组合模块不暗加寄存器；S1 寄存器由 lane 内 `dp_lane_unpack` 持有，其余流水由 lane、group、top 三层持有。同步低有效 `rst_n` 清除有效控制并取消在途请求；数据寄存器以有效使能保持，不进行全数据复位。握手、阶段映射、源文件和统计归属见 [RTL 实现合同](../spec/dp/implementation/verilog.md)。

尾数定点格式注释使用对齐表格，每行一种或一类精度，独立列出 S、I、F。表前说明 SM 独立符号或 TC 二补码，以及 P、L 等参数的定义。乘法器输入和输出分别列出各自的 S、I、F。解包和尾数乘法表列有效 coefficient 的格式；通用槽的高位零扩展不增加 F，树和级间输出表按数值通路宽度列示。

## 纯 Verilog 排版

文件、模块、实例和信号命名遵循 [dp-naming-convention](../../.skill/dp-naming-convention/SKILL.md)。局部数值不得只叫 `e/f/a`，应按实际含义写 `exponent_field/fraction_field/product_even` 等；互联线明确驱动方和接收方，模块端口保留 `in_`/`out_`。维护中的主/E RTL 已按 v1.6 迁移；历史 SV 与旧快照保留原名。

遵循 [dp-rtl-code-style skill](../../.skill/dp-rtl-code-style/SKILL.md)。`*.v` 使用两空格缩进、LF 换行、100 列目标行宽，**每条声明只定义一个变量**。端口每行重复完整方向、类型和位宽；`wire/reg/parameter/localparam` 等也分别声明，取代此前同类变量合并的约定。

```verilog
input wire in_a_valid,
input wire in_b_valid,
input wire in_c_valid,
input wire [K_FP16*`DP_HALF_W-1:0] in_a,
input wire [K_FP16*`DP_HALF_W-1:0] in_b,
```

先拆分声明，再用 Verible `v0.0-4298-g085eef05` 格式化本次涉及的维护文件。下面命令中的文件路径替换为本次修改的文件，不批量触及冻结 SV、历史快照或用户无关改动。formatter 不保证自动拆开多变量声明，不再用 `verilog_format: off/on` 保护旧式合并声明。

```sh
verible-verilog-format --inplace --failsafe_success=false \
  --indentation_spaces=2 --wrap_spaces=2 --column_limit=100 --try_wrap_long_lines \
  --formal_parameters_indentation=indent --port_declarations_indentation=indent \
  --named_parameter_indentation=indent --named_port_indentation=indent \
  src/verilog/top/dp_top.v
```

现用多精度与 E RTL 已采用同步低有效 `rst_n`，全部流水由 `common/` 参数化 DFF 保存。控制同步复位，payload 无复位、有效时更新；边界实例命名为 `ff_sN_sM_<field>`。详见 [寄存器合同](../../.skill/dp-rtl-code-style/references/registers.md) 和 [v1.6 验证](../../test/results/dp-style-v1.6.md)。冻结 SV 保留旧 reset 接口，旧快照及 PPA 结论不变。

## 验证

先按 [CModel 说明](../cmodel/README.md) 构建参考模型，然后从仓库根目录运行：

```sh
# 默认：Verilator + 纯 Verilog DUT；不运行历史 SV
python3 test/run_verilog.py --phase all

# E-only：MXFP4/NVFP4/HiF4，E64，L8/II1
python3 test/run_verilog.py --frontend e --phase all

# 显式选择主实现；Verilator 可通过参数或 VERILATOR 环境变量指定
python3 test/run_verilog.py --implementation verilog --verilator /path/to/verilator

# 独立四态仿真及严格 Verilog-2005 语法检查
python3 test/run_verilog.py --simulator iverilog --implementation verilog
```

[dp_tb.v](../../test/rtl_tb/dp_tb.v) 直接读取共用 `DP_INPUTS_V1`，逐笔检查 D/type/last、L8、原子 ready、气泡、复位及非法元组拒收。它输出 `results.txt` 和 `PASS` 统计；参数回归还输出 S1–S7 断点，与 CModel trace 比较。脚本另用独立调度队列核对输出顺序。只有显式选择 `--implementation both` 时才做历史双版输出指纹比较；新版本不要求与冻结 SV 同步。

每次验证先将源代码冻结到 `hw/rtl/DP_<implementation>_<fingerprint>/`，保存 portable `files.f`、源/快照 SHA、RTL_ID、README、参数与验证范围。运行日志、构建产物、逐笔输出和断点在 `test/runs/verilog/`，不提交。精简证据见 [RTL 报告](../../test/results/verilog-v1.4.md)。

RTL 单独执行 `-Wall` lint，位宽、锁存器、组合环类警告不豁免。非功能豁免仅限 `UNUSEDSIGNAL`（显式冗余位/观察点）、`UNUSEDPARAM`（共用格式表）、`VARHIDDEN`（Verilog 共享函数头在各模块独立展开）。TB 编译另外允许 integer 文件读取宽度、timescale 和初始化调度告警；这不替代前述 RTL lint。

## 当前边界

当前两种前端只开放 L8；CModel 的 L9 探索未在 RTL 中开放。冻结 SV 的范围由其历史说明定义。未实现 Chisel、DP-Group、TensorCore/Cube、Q/QE、混合组或独立对齐方案。历史 27/40 的 N12 TT 在 1.41 GHz setup 未达标；逐级证据与 1GHz 后续测量见 [时序分析](../../hw/dc_syn/records/dp_n12_timing_20261105.md)。E64 与当前 28/40 多精度单元的同工况测量见 [DC 对比](../../hw/dc_syn/records/e64_n12_comparison_20261105.md)。尚无布局布线或真实活动功耗。

DC 接入使用 [统一门禁与流程](../../hw/dc_syn/README.md)。Verilog 的运行时 `lane_fraction` 已改为等价常量选择以兼容 DC；新快照重新完整回归，不继承旧 snapshot 的通过状态。

## E64 专用层级

`dp_top_e → dp_group_e ×4 → dp_lane_e ×2/group → dp_lane_unpack_e ×2/lane`。E lane/group 不实例化原多精度 bank 或宽局部移位器：S1 FP4/e1 解码，S2 4×4＋pair10，S3 lane12，S4 lane 小左移/组和/abs 至幅值14，S5 scale14×8 或 MX 旁路后补零到 M31。SIF 在相应源码中按精度分行列示。

顶层保持原请求端口和 K_FP16/LOCAL_W/GLOBAL_W 参数，便于接口复用；只接受三个 E datatype 和 FP32 C。K_FP16 仅为容量索引，4/8/16 对应 E16/E32/E64。LOCAL_W 影响公共 token 容器和补零，E 的内部自然位宽不随其扩大。后端复用已有 C 解包、全局移位、树和 FP32 舍入模块定义，流水寄存器由两个 top 分别持有；没有额外 dp_backend.v 或通用混合组实现。

[完整测试结果](../../test/results/e64-v1.5.8.md)按用户要求长期保留；原始输入/输出、断点、编译与仿真日志放在显式 run，快照放在 hw/rtl，网表保留在 DC run，不提交大型产物。

E 元素解包独立位于 [unpack/dp_lane_unpack_e.v](unpack/dp_lane_unpack_e.v)，每份组合模块处理一侧32位操作数、HiF4 e1并输出幅值/符号；S1 寄存器继续在 dp_lane_e，e2 控制也由 lane 持有，不增加延迟。显式 files_e.f 包含15个 `.v`。多精度 dp_lane_unpack 保持原样。模块化后的新快照需重新验证，历史 DC 测量仅属于原快照。
