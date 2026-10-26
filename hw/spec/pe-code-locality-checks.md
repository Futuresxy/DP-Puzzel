# PE计算代码归属重构与检查

2026-10-24。范围由用户明确选择：H/Q完整展开；HQE/QE/E保留SubPE/PEGroup，只将Utils中的PE专属计算移回PE文件。本批次不实现阵列、不改变既有数值/周期合同。

## 当前代码结构

- `PE_H.scala`直接展示16路FP16/BF16解包、11×11乘法、全K MAX/RTZ、自然位宽累加和最终输出。
- `PE_Q.scala`直接展示32路FP8/FP6转换、4×4乘法、公共E8M0 scale指数、全K MAX/RTZ和累加。
- H/Q不再有DataUnpack/SubPE/PEGroup实例，g4名称仅保留输入布局兼容性。
- HQE/QE/E保留本族DataUnpack/SubPE/PG模块，PE文件直接展示packed输入/scale切片、S07 MAX、S08对齐、S09和及S10/S11输出。
- 删除Utils中的PEWiring、PEAlignNormalize、PEGlobalAlignNormalize、RawProductInterfaces及对应镜像spec，移除未使用的PE placement/scale slot辅助函数和H/Q SubPE参数分支。
- 通用MAX、RTZ移位、CSA和PENormalizeExact继续复用。输出F=pe_align_width、PE 11级、K/MN 18级保持原合同。

源码入口及逐文件解释见[导航](../chisel_src/README.md)和[六种PE设计](six-pe-design.md)。最初来源记录`six-pe-source.json`中的H/Q旧目标属于迁移基线，当前模块映射以新导出manifest为准。

## 编译、结构及来源

Mill0.11.8、Scala2.13.12、Chisel6.4.0、firtool1.62.0；Scala编译和warnings-as-errors的35组CHIRRTL参数/布局展开通过，11组非法配置按require拒绝。42个Scala文件与42个镜像spec一一对应。H/Q无PG/SubPE；HQE/QE/E保留原实例数；各PE直接实例化通用PENormalizeExact。生成module同名文件、源码映射、files.f和输入hash均检查。

重构前源SHA-256：`265509a97285a1b3f78df33fa4ed119437e9fc8a392e4f010187a6334b6e92a4`。当前源SHA-256：`a7e47e9b933181e3127c938990bc8ef12fcd757b347bee75df9fe054bacc5926`。当前八份导出逐文件源码/build hash均与工作树一致。manifest均保持`generated`、`rtl_test=not_run`、`ppa_eligible=false`。

## RTL逐拍比较

仿真器：Icarus Verilog version 12.0 (stable) ()。脚本[check_pe_refactor.py](../../scripts/check_pe_refactor.py)分别编译两份显式导出，使用同一SV testbench和stimulus，不复制或修改设计RTL。输入集合为每个配置可支持的全部合法A/B格式类型对，每对64个输入周期，seed=`0x5eed27`；包含一般编码、指定特殊/边界码、非单位scale、HiF4 g0/g1、连续输入、气泡、在途复位和重新配置。K/MN额外覆盖AB/C原子接收、last及不同C类型/舍入配置。

逐拍比较所有可见控制和有效数值/标志；无效payload不作数值比较。另用独立valid/last移位scoreboard检查11/18个寄存边界。所有表内比较通过，共10,346拍、4,455个有效输出。

| 基线export ID | 当前export ID | 比较拍数 | 有效输出数 | 固定周期 |
| --- | --- | --- | --- | --- |
| PE_H_g4_10242019 | PE_H_g4_10242029 | 205 | 88 | 11 |
| PE_Q_g4_10242019 | PE_Q_g4_10242030 | 1465 | 704 | 11 |
| PE_HQE_g4_10242019 | PE_HQE_g4_10242030 | 2095 | 1012 | 11 |
| PE_QE_g4_10242019 | PE_QE_g4_10242030 | 1915 | 924 | 11 |
| PE_E_g4_10242019 | PE_E_g4_10242030 | 475 | 220 | 11 |
| PE_E_g2_10242019 | PE_E_g2_10242030 | 475 | 220 | 11 |
| MN-PE_H0Q32E0_10242019 | MN-PE_H0Q32E0_10242030 | 1529 | 528 | 18 |
| K-PE_H16Q32E96_10242019 | K-PE_H16Q32E96_10242030 | 2187 | 759 | 18 |

现有独立单位值SV smoke在六个当前基础PE导出上再次通过，共448项有效输出比较；覆盖单位scale下−1/0/+1的坐标/符号/零/特殊标志预期及11级valid。

## 复现与保留

```sh
cd hw
mill -i pe.runMain dp.elaborate.Elaborate review
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/pe_h_g4.json "PE code locality review"
cd ..
python scripts/check_pe_export.py PE_H_g4_10242029 --smoke
python scripts/check_pe_refactor.py PE_H_g4_10242019 PE_H_g4_10242029
```

生成命令创建新export ID，不覆盖表内输入。比较脚本每次要求新的run目录；同一对导出的既有run须先按引用关系归档，不能覆盖证据。所有本批基线/当前RTL均因比较记录引用而保留；仿真可执行文件已在成功后删除。精简[JSON摘要](../test/regressions/pe-code-locality-summary.json)保存manifest/filelist/source指纹、seed、格式对、TB/stimulus/checker/trace/报告hash及逐项复现命令；完整TB、stimulus和日志在摘要的忽略run目录。中途通过的预备导出另留本地原有记录，不作为最终源码证据。

## 限制

这是有限输入集合上的重构行为一致性检查，旧RTL不是独立精度oracle，不能证明所有编码/事务形式严格等价，也不能消除基线已有数值问题。既有单位值smoke同样不是完整精度回归。

本批RTL只测试默认28/2/40/40窗口；其他合法参数变体仅完成展开。完整独立数值参考、误差/质量门槛、所有参数的RTL精度/协议验收、真实负载、DC时序/面积和功耗均未在本批完成；不升级为passed或PPA eligible。HiF4外部规范版本仍待确认。
