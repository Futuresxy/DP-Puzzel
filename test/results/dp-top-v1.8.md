# dp_top v1.8 验证记录

## CModel 检查点

- 合同提交：`75b0524`；仅 `frontend=multi` 默认启用 v1.8。其他前端维持 v1.7；`legacy_multi=true` 用于旧混合组与回放。
- 构建：`.deps/cmake-3.28.4/bin/cmake --build src/cmodel/build -j 2`，通过。
- `python3.11 test/run_cmodel.py --phase all`：11 种格式 10,747 笔，架构失配 0，原有 expected.jsonl 匹配；结果见 [摘要](dp-top-v1.8-cmodel.json)。运行 `20261109T094153935929Z`。
- `python3.11 -m unittest discover -s test/tests`：41 项通过。新增 HiF4 lane e2 组合/抵消、C 非正规非 FTZ、无偏 scale 与旧 E 最终结果对照。
- 精确数学参考 `test/reference/exact.py` 和保存的 golden 未改动。v1.8 有限窗口参考隔离在 `test/reference/architecture.py`；非正规 C 的 MAX 键为 -126，极小值的截断可能与旧版不同。
- HiF4 e2=0 的最大输入组幅值由旧 F6 的 12544 改为 F4 的 3136；实数值保持一致。相应中间格式断言按合同更新。
- 历史 E/QE/混合断点对照显式使用 legacy 模式，不强制其迁移到新中间格式。

## RTL 验收

- 冻结快照：`DP_verilog_e84d765a8a29dc88`，目录指纹 `02c70395309c90e2ad47f7bcb11b4554db15a3f3bad2baba285c579745dfc474`。
- 正式回执：`test/runs/verilog/20261109T095602174363Z/verification.json`。摘要见 [RTL JSON](dp-top-v1.8-rtl.json)。`scripts/rtl_gate.py` 当前源码门禁已通过。
- 11 种格式原有 10,747 笔全部通过；FP16 最大 1 ULP、BF16 最大 3 ULP，MXFP4/NVFP4/HiF4 最大 0 ULP（仅限本批数据）。
- 六组参数：K4/27/40、K8/27/40、K16/28/40、K4/28/48、K8/32/64、K16/32/64。每组 accepted=528、checked=487、reset_cancelled=41；逐拍混型、气泡、复位、非法元组和 L8/II=1 检查通过。
- 新增定向 5,314 笔：FP4 编码乘积、e1/e2、不同 lane 的 e2、抵消、scale 编码及 C 非正规/特殊边界。RTL/CModel 及数学精确结果全部一致；1,095,599 个 S1–S7 断点通过，包括 S3 提前 anchor 和 S5 compare_exp。
- S7 压缩器附加验证：N=2/3/5、W=3 全输入穷举；W=40/64 边界及固定种子随机，共 45,392 组。见 [CSA 摘要](dp-top-v1.8-csa.json)。它补充而不代替冻结 RTL 的 Verilator 验收。
- 六个未迁移顶层仅做兼容 lint，均通过；本轮未对它们生成新功能/PPA 验收。
- 门禁增加 v1.8 的第18项定向覆盖及新增断点数检查。新版快照不能复用17项旧合同；旧功耗快照的门禁合同仍保留。DC 输入门禁的12项负向测试通过。

复现命令（本机已安装工具）：

```sh
PATH=/opt/rh/gcc-toolset-10/root/usr/bin:$PATH \
CCACHE_DISABLE=1 CXXFLAGS='-std=c++20 -fcoroutines' \
MAKEFLAGS='OPT_FAST=-O0 OPT_SLOW=-O0' \
python3.11 test/run_verilog.py --implementation verilog --phase all \
  --verilator /eda/verilator/v5.030/bin/verilator
python3.11 scripts/rtl_gate.py DP_verilog_e84d765a8a29dc88
```

宿主工具说明：系统 Verilator/GCC 版本不足以使用当前 timing TB。GCC10 的默认优化构建在 K8/32/64 仿真起始协程处出现段错误；关闭宿主优化和缓存重建后，同一输入通过，最终完整回归使用上列设置。该设置仅影响仿真 C++，不改变 RTL 或综合优化。首次新定向测试超过 TB 的旧2048行容量，已扩为8192行。

断点验证修正：取消 C LZD 后，CModel 仍需对零/特殊 C 清除无效 anchor；现已按 RTL 合同清为0，并增加专门测试。有限非零 C 的原始指数和幅值保持。

本批没有运行新 DC/功耗；v1.8 的 S4 树后 e2、S5 LZD 后减法和 S7 CSA/CPA 的1GHz可行性仍须综合验证。不能使用旧 PPA 宣称本次改动已取得时序或功耗收益。
