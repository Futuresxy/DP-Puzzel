# 新版共用验证环境

**v1.4 当前状态：** 已接入分组共享 DP CModel、统一packed输入和独立精确参考。先测试原九格式，再扩展 TF32/INT8。三实现共享数据合同见 [数据说明](data/README.md)，首批结果见 [报告](results/cmodel-v1.4.md)；新增 [标准 Verilog TB](rtl/README.md) 与 [两版 RTL 验证](results/verilog-v1.4.md)。

| 目录 | 职责 |
| --- | --- |
| [cases/](cases/README.md) | 共用用例、逻辑输入及控制事件、固定种子 |
| [reference/](reference/README.md) | 独立数学参考与精度分析 |
| [rtl/](rtl/README.md) | 标准 Verilog 驱动、原子握手检查、L8 scoreboard、S1–S7 断点 |
| [adapters/](adapters/README.md) | CModel 与两条 RTL 路径的薄适配层 |

共用激励、调度、检查规则及报告，按实现选择后端。两套 RTL 对 CModel 的实现一致性要求与相对数学参考的精度指标分别验收；具体合同由 spec 定义。

生成结果放入 `test/runs/`（忽略提交）。设计 RTL 只读取 `hw/rtl/` 的显式导出，不在本目录复制另一份。DC 流程自身的校验测试位于 `hw/dc_syn/tests/`。

## 可执行入口

先按 [CModel README](../src/cmodel/README.md) 构建，然后执行：

```sh
python3 test/run_cmodel.py --phase existing
python3 -m unittest discover -s test/tests -p test_existing.py -v
python3 test/run_cmodel.py --phase extensions
python3 -m unittest discover -s test/tests -v
```

回归分别要求：C++对独立有限窗口参考逐位一致、数学误差落在逐例推导上界内、INT8精确回绕；另外比对已保存golden。TF32同时记录FP64近似参考。`--phase all` 可重跑全部10747笔；详细报告生成到 `runs/cmodel/<phase>/`。

## 手写 RTL 回归

```sh
python3 test/run_verilog.py --phase all
python3 test/run_verilog.py --simulator iverilog --implementation verilog --phase all
```

默认使用 Verilator，同时编译 Verilog 与 SystemVerilog 两个独立实现，共用 `rtl/dp_tb.v`。测试前冻结 `hw/rtl/DP_<implementation>_<fingerprint>/`；脚本不直接编译可变源码。结果、日志和构建产物在 `test/runs/verilog/`，逐笔输出为 `id result_hex result_type last`。参数回归同时比较 CModel 的 S1–S7 数值断点；实现对照使用输入/输出文件指纹。详见 [运行说明](../src/verilog/README.md)。
