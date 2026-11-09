# dp_top v1.8 验证记录

## CModel 检查点

- 合同提交：`75b0524`；仅 `frontend=multi` 默认启用 v1.8。其他前端维持 v1.7；`legacy_multi=true` 用于旧混合组与回放。
- 构建：`.deps/cmake-3.28.4/bin/cmake --build src/cmodel/build -j 2`，通过。
- `python3.11 test/run_cmodel.py --phase all`：11 种格式 10,747 笔，架构失配 0，原有 expected.jsonl 匹配；结果见 [摘要](dp-top-v1.8-cmodel.json)。运行 `20261109T092913951470Z`。
- `python3.11 -m unittest discover -s test/tests`：40 项通过。新增 HiF4 lane e2 组合/抵消、C 非正规非 FTZ、无偏 scale 与旧 E 最终结果对照。
- 精确数学参考 `test/reference/exact.py` 和保存的 golden 未改动。v1.8 有限窗口参考隔离在 `test/reference/architecture.py`；非正规 C 的 MAX 键为 -126，极小值的截断可能与旧版不同。
- HiF4 e2=0 的最大输入组幅值由旧 F6 的 12544 改为 F4 的 3136；实数值保持一致。相应中间格式断言按合同更新。
- 历史 E/QE/混合断点对照显式使用 legacy 模式，不强制其迁移到新中间格式。

本检查点仅为 CModel 验证；RTL/时序/面积/功耗尚未验收。
