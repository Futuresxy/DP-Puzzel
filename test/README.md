# 新版共用验证环境

**v1.4 当前状态：** 已接入分组共享 DP CModel、统一packed输入和独立精确参考。先测试原九格式，再扩展 TF32/INT8。三实现共享数据合同见 [数据说明](data/README.md)，首批结果见 [报告](results/cmodel-v1.4.md)；新版 RTL TB 尚未实现。

| 目录 | 职责 |
| --- | --- |
| [cases/](cases/README.md) | 共用用例、逻辑输入及控制事件、固定种子 |
| [reference/](reference/README.md) | 独立数学参考与精度分析 |
| [tb/](tb/README.md) | SV 驱动、协议 monitor、scoreboard |
| [adapters/](adapters/README.md) | CModel 与两条 RTL 路径的薄适配层 |

共用激励、调度、检查规则及报告，按实现选择后端。两套 RTL 对 CModel 的实现一致性要求与相对数学参考的精度指标分别验收；具体合同由 spec 定义。

生成结果放入 `test/runs/`（忽略提交）。设计 RTL 只读取 `hw/rtl/` 的显式导出，不在本目录复制另一份。原 `hw/test/` 保留旧验证资料，其用例、误差阈值及通过状态不自动继承。

## 可执行入口

先按 [CModel README](../src/cmodel/README.md) 构建，然后执行：

```sh
python3 test/run_cmodel.py --phase existing
python3 -m unittest discover -s test/tests -p test_existing.py -v
python3 test/run_cmodel.py --phase extensions
python3 -m unittest discover -s test/tests -v
```

回归分别要求：C++对独立有限窗口参考逐位一致、数学误差落在逐例推导上界内、INT8精确回绕；另外比对已保存golden。TF32同时记录FP64近似参考。`--phase all` 可重跑全部10747笔；详细报告生成到 `runs/cmodel/<phase>/`。
