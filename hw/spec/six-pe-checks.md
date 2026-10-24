# 六种基础PE本轮检查记录

2026-10-24，新加坡时区；当前工作分支fix/full-reuse-hierarchy-migration，源基准Git为6522618cb78dac9bc2f64c11e00365e730435b95。下面导出在本轮修改尚未提交时生成，manifest如实记录git_dirty=true。

本轮覆盖五族六profile迁移、H/Q全局对齐改造、公共坐标与参数传递，以及用户要求的短目录命名。**不是完整RTL精度验收，也未执行DC/power。** 总设计见[六种PE设计](six-pe-design.md)，来源与原工程固定版本见[six-pe-source.json](six-pe-source.json)。

## 编译与展开

- Mill0.11.8、Scala2.13.12、Chisel/plugin6.4.0、firtool1.62.0；Scala编译通过，warnings-as-errors。
- 52个Scala文件与52个镜像spec一一对应，没有遗留的孤立逐文件spec。
- CHIRRTL展开35个配置：6个基础PE、6个MN、4个K布局；六profile各三组窗口变体，以及HQE_g4+E_g2的最大窗口K变体。核对PG/SubPE数量。
- 11个非法参数/profile/布局构造均由require拒绝。参数范围为26..30/2..4/38..48/38..48，top窗口不得小于PE窗口。
- skill元数据校验及git diff空白检查通过。

```sh
cd hw
mill -i pe.compile
mill -i pe.runMain dp.elaborate.Elaborate review
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/k_1_2_6.json "six-pe-review"
```

## split RTL与有限SV定向检查

最终源码指纹为`265509a97285a1b3f78df33fa4ed119437e9fc8a392e4f010187a6334b6e92a4`，包含52个Scala文件、build.sc与.mill-version。新命名仅简化目录，完整源hash、参数/布局/config hash、时区和UTC时间仍保留在manifest中。模块同名.sv和源码映射不变。

[机器可读摘要](../test/regressions/six-pe-smoke-summary.json)绑定以下12个显式export ID，参数列依次是Q字内窗口/PG guard/PE窗口/top窗口。每份都检查files.f和所有输入hash、每文件一个同名module、实际PE→PG→SubPE实例数、专用H/Q全局规约与共享/E分级规约。PE输出magnitude必须为PE窗口+1，anchor为11位；K/MN核对top窗口寄存器和自然加法增长、共享C/D各一份。

| export ID | 参数 | SV定向比较数 |
| --- | --- | --- |
| PE_H_g4_10241551 | 28/2/40/40 | 32 |
| PE_Q_g4_10241551 | 28/2/40/40 | 64 |
| PE_E_g2_10241551 | 28/2/40/40 | 48 |
| PE_E_g4_10241551 | 28/2/40/40 | 48 |
| PE_HQE_g4_10241551 | 28/2/40/40 | 144 |
| PE_QE_g4_10241551 | 28/2/40/40 | 112 |
| K-PE_H16Q32E96_10241551 | 28/2/40/40 | 结构检查 |
| MN-PE_H0Q32E0_10241551 | 28/2/40/44 | 结构检查 |
| PE_E_g2_10241552 | 28/2/44/44 | 48 |
| PE_Q_g4_10241552 | 26/2/38/38 | 64 |
| PE_QE_g4_10241552 | 30/4/48/48 | 112 |
| K-PE_H16Q32E96_10241552 | 30/4/48/48 | 结构检查 |

9份基础PE导出用Icarus Verilog 12.0编译并执行SV testbench，共672项有效输出比较。覆盖每族合法元素模式、单位scale、−1/0/+1输入、全正/全负/全零/混合符号、初始复位、连续valid与气泡；确定种子0x5eed。独立整数点积参考计算magnitude/sign/anchor/zero/special预期，并检查11级valid。g2/g4分别按同一F窗口比对，g2硬件额外assert输出最低位为零。

```sh
python scripts/check_pe_export.py PE_H_g4_10241551 --smoke
python scripts/check_pe_export.py K-PE_H16Q32E96_10241551
```

短目录后缀`MMddHHmm`使用Asia/Singapore，已由manifest的created_utc独立换算核对全部12个ID；重复同容量/同分钟的K导出被拒绝，原目录全部文件hash保持不变。检查器另用一次性副本验证RTL hash损坏会拒绝；即使重算文件hash，缺失PG实例仍会被拓扑检查拒绝。副本随后删除，未修改验证输入。

初次H导出遇到本机Icarus不支持firtool默认的automatic block-local变量；已在生成器启用disallowLocalVariables并重新生成，无手工修改RTL。此前本轮长名称试导出已被本批替代，清理其生成src/files.f与无用仿真可执行文件，保留manifest/README和必要工具错误日志；历史Full迁移证据未改动。

## 尚未验收的内容

- 未覆盖一般浮点尾数/指数、非单位scale、特殊值全部组合、subnormal/溢出/下溢、严重抵消、一般RTZ误差与完整随机参考回归。统一layout/F和11级valid不能证明H/Q与多级复用路径误差相同。
- K/MN仅完成编译/展开/结构检查；完整C/D数值、batch握手、排空/复位等RTL周期协议回归尚未执行。18级仍是实现/spec合同，不作为本轮SV已全面验收的结论。
- 所有导出维持generated、rtl_test=not_run、ppa_eligible=false；672项定向通过不升级为passed。PPA门禁、工艺库/时序/真实负载功耗未接入，未产生面积、功耗或性能测量。
- 不包含阵列广播、脉动连接、L0、调度器或多输出阵列；阵列实现继续等待单独方案审核。
