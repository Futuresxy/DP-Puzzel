# 当前工作流验收：2026-10-24

使用 v2 单个 RTL 目录指纹与简洁摘要；默认开启 clock gating，保留模块和 PE 子树，支持按深度、模块和实例选择展开。DC 唯一公共入口为 scripts/dc_syn.sh，所有 testbench、测试配置、参考和流程软件回归统一放在 hw/test。

- 软件：Python 3.6.8 / 3.11 下 21 项通过；覆盖目录内容与清单变化、回归过期、短名/时区/重名拒绝、配置快照、PE 子树保护、三种展开选择、核心记录、时序 FAIL/UNKNOWN、缺库/缺报告、清理边界和 Python 3.6 导出兼容。
- 静态：Python 编译、Shell 语法、Tcl 完整性及策略行为、skill 校验、文档链接和 diff 检查通过。软件夹具不代表硬件测量。
- 真实 RTL：Icarus 检查 132423 周期、131867 有效结果，含全部 BF16 编码 × 两种操作、定向/随机、气泡和复位。
- 真实 DC：dc_Bf16SignPipe_10241850，DC X-2025.06、N22 TT 0.9 V/85°C、1410 MHz；面积 42.434 µm²，setup/hold PASS，未约束检查 clean。
- 真实门控：1 个工具插入的时钟门控单元，16 个寄存器受门控；剩余 1 个有效位寄存器不门控。
- 产物：当前 PR 只保留最新示例 run 及其 RTL/验证证据；删除无下游引用的旧示例产物和重复入口。清除当前 work 缓存，保留原始报告和 mapped Verilog/SDC/DDC。

软件检查命令：`python3 -m unittest discover -s hw/test/unit -v`。核心数据见 [records](records/bf16_sign_pipe_smoke_20261024.json)，复现见 [示例](examples/bf16_sign_pipe/README.md)。例子不含 PE 阵列；PE 选择策略由 Tcl 行为测试覆盖，实际 PE 面积/功耗仍须在相应设计上验收。尚未执行布局布线、workload power 或 RTL/netlist 等价性验证。
