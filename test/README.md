# 新版共用验证环境

**当前状态：** 已接入分组共享 DP CModel、统一packed输入和独立精确参考。先测试原九格式，再扩展 TF32/INT8。CModel 与现用 Verilog 的共享数据合同见 [数据说明](data/README.md)，首批结果见 [报告](results/cmodel-v1.4.md)；新增 [标准 Verilog TB](rtl_tb/README.md) 与 [历史 RTL 验证](results/verilog-v1.4.md)。

| 目录 | 职责 |
| --- | --- |
| [cases/](cases/README.md) | 共用用例、逻辑输入及控制事件、固定种子 |
| [reference/](reference/README.md) | 独立数学参考与精度分析 |
| [rtl_tb/](rtl_tb/README.md) | 标准 Verilog 驱动、原子握手检查、L8 scoreboard、S1–S7 断点 |
| [adapters/](adapters/README.md) | CModel 与现用 Verilog 的薄适配层；保留显式 SV 历史重放 |

共用激励、调度、检查规则及报告，按实现选择后端。现用 Verilog 对 CModel 的实现一致性与相对数学参考的精度分别验收；SV 已冻结为历史参考，不再作为新功能的同步维护对象。具体合同由 spec 定义。

混合 DP 的 E96/E128/E192/E256、Q64/Q96/Q128 共23064笔[逻辑向量及数学 golden](data/README.md#逻辑-k-扩展数据-dp_logical_vectors_v1)。它们使用独立 `inputs.jsonl` schema，各profile按原生K选择对应语料，已接入 CModel/RTL；每profile完整语料仍为11格式10747笔。数据校验入口为 `python3.11 -m unittest discover -s test/tests -p test_logical_vectors.py -v`。

生成结果放入 `test/runs/`（忽略提交）。CModel 和 RTL 各保留最近两次普通运行，重要证据与用户确认后标记保留。结果确认后按 [运行产物保留](../scripts/README.md#运行产物保留) 清理。设计 RTL 只读取 `hw/rtl/` 的显式导出，不在本目录复制另一份。DC 流程自身的校验测试位于 `hw/dc_syn/tests/`。

## 可执行入口

先按 [CModel README](../src/cmodel/README.md) 构建，然后执行：

```sh
python3 test/run_cmodel.py --phase existing
python3 -m unittest discover -s test/tests -p test_existing.py -v
python3 test/run_cmodel.py --phase extensions
python3 -m unittest discover -s test/tests -v
python3 test/run_cmodel.py --frontend e --phase all
```

回归分别要求：C++对独立有限窗口参考逐位一致、数学误差落在逐例推导上界内、INT8精确回绕；另外比对已保存golden。TF32同时记录FP64近似参考。`--phase all` 可重跑全部10747笔，默认每次生成独立的 `test/runs/cmodel/<UTC-run-id>/`。

E 前端复用 MXFP4/NVFP4/HiF4 三种各 961 笔数据，分别与保存的多精度结果和精确数学参考比较。`test_e_frontend.py` 检查 E 内部切点、HiF4 坐标映射及共用后端，E 回归禁止 `--write-goldens`，不覆盖多精度期望。E RTL 使用同一 TB 和调度/数值检查器，选择 `--frontend e` 驱动 dp_top_e；默认仍为多精度主实现。

## 手写 RTL 回归

```sh
python3 test/run_verilog.py --phase all
python3 test/run_verilog.py --frontend e --phase all
python3 test/run_verilog.py --implementation verilog --phase all --local-w 29 --global-w 33
python3 test/run_verilog.py --simulator iverilog --implementation verilog --phase all
```

默认使用 Verilator，只编译纯 Verilog DUT，使用 `rtl_tb/dp_tb.v`。显式 SV/双版选项只作 [冻结版本参考检查](../src/verilog/systemverilog/README.md)，后续新特性不要求 SV 一致。测试前冻结 `hw/rtl/DP_<implementation>_<fingerprint>/`；脚本不直接编译可变源码。结果、日志和构建产物在 `test/runs/verilog/`，逐笔输出为 `id result_hex result_type last`。参数回归同时比较 CModel 的 S1–S7 数值断点；显式双版参考检查额外比较输入/输出文件指纹。详见 [运行说明](../src/verilog/README.md)。

默认局部/全局窗口为 28/40。使用 `--local-w` 和 `--global-w` 可分别扫参；固定数据集仍为 K16。自选窗口用同配置 CModel 重算 `golden_exact` 的期望，数学参考和提交的 golden 文件保持原样。自选回归只记录功能验证；使用默认配置完整回归可重建 DC 门禁回执。

命令行按实现逐项显示完整数据集结果。默认配置下，`golden_exact` 是实际 RTL 输出与 `expected.jsonl` 的 `d` 字段逐位一致的数量，该字段保存已验证的有限位宽 CModel 结果。`math_exact` 对比同文件的 `exact_fp32_or_int32`。`max_ulp` 统计有限 FP32 输出与数学参考之间的最大 ULP 距离，INT8 显示 `n/a`。特殊值仍计入逐位一致数。两项数学统计用于查看精度，RTL 的通过条件是逐位匹配有限位宽 golden 和满足协议。

九种原有浮点编码各 961 笔，INT8 为 1045 笔，TF32 为 1053 笔。混格式参数回归单独生成每种格式 48 笔，现场调用 CModel，并插入气泡和复位来覆盖协议。`reset_cancelled` 表示已接收但在输出前被复位清空的请求数。最终打印完整 JSON 报告路径。

## 现用混合配比顶层（v1.7.6）

新增 `dp_lane_qe` / `dp_group_qe` 与三个现用混合 profile；详见 [混合架构](../src/spec/dp/dptop/mixed-precision-expansion.md)。

```sh
python3.11 test/run_mixed_verilog.py --frontend t8h16q32e96
python3.11 test/run_mixed_verilog.py --frontend t8h16q32e128
python3.11 test/run_mixed_verilog.py --frontend t8h16q64e128_opt
```

每个顶层独立导出和 lint，完整运行11种精度的10747笔原生数据，再运行三组窗口的混格式/边界/协议/断点测试。`golden_exact` 使用本 profile 现场 CModel，`math_exact/max_ulp` 使用提交的独立数学 golden；不会覆写数据中的历史期望。验证记录见 [混合 RTL 验证](results/mixed-rtl-v1.7.md)。

## E64 / Q32E64 独立顶层

在已有 CModel/Verilator 构建环境下：

```bash
python3.11 test/run_lowp_verilog.py --frontend e64
python3.11 test/run_lowp_verilog.py --frontend q32e64
```

每支持格式961笔，另测27/40、28/40、32/64三个窗口的S5–S7断点和L8协议；独立快照、门禁回执见 [v1.7.4](results/lowp-tops-v1.7.4.md)。该入口不调用DC或功耗工具。

## Q 专用扩展验证 v1.10

`t8h16q64e64` 使用四种 Q64 原生语料及其余基础精度语料，11格式共10747笔；完整 RTL 回归另含27/40、28/40、32/64三个窗口的断点和周期检查。专项覆盖 Q→E 连续切换、失活扩展旧 NaN/Inf/大指数、负零、NaN scale×Inf 的 S5 标志、Q 乘积寄存保持和复位取消。

```sh
source /opt/rh/gcc-toolset-10/enable
CCACHE_DISABLE=1 CXXFLAGS='-std=c++20 -fcoroutines' python3.11 test/run_mixed_verilog.py \
  --frontend t8h16q64e64 --verilator /eda/verilator/v5.030/bin/verilator
```

本机工具环境如上，其他环境可用 `--verilator` 指定路径并配置支持 coroutine 的编译器。完整结果见 [本轮回执](results/q-only-v1.10-20261112.md)；功能通过不代表新顶层达到1GHz或1.41GHz。CModel新profile拒绝legacy合同，专项检查位于 `tests/test_q_only_frontend.py`。

## E192/E256 验证 v1.11

`test/run_mixed_verilog.py --frontend t8h16q32e192|t8h16q32e256` 各检查 11 格式10747笔原生数据，以及三窗口、S2–S7断点、门控、L8/II=1、气泡和复位。三种 E 格式采用新导入的 K192/K256 原生961条输入与独立数学golden，不拼接较小K。专用模型检查为 `tests/test_e_expansion.py`；冻结算术补充检查 `check_mixed_csa.py --export-id <id> --report <json>` 覆盖扩展2/4/8/12及叶宽3/40/64、失活毒化与正负增长位。[完整记录](results/e192-e256-v1.11-20261112.md)。

## T8H16Q96E192/T8H16Q128E256 验证 v1.12

`run_mixed_verilog.py --frontend t8h16q96e192|t8h16q128e256` 分别选择四种 Q96/Q128 与三种 E192/E256 原生数据，并执行三窗口断点、逐拍类型切换、失活组毒化、各 Q32 scale 边界、负零、气泡与复位取消检查。[冻结回执](results/qe-expansion-v1.12-20261112.md)保留原输入和完整来源。
