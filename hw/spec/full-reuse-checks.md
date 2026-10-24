# Full 复用基线检查记录

> 历史Full迁移记录，当前基线见 [六种PE设计](six-pe-design.md)。本页证据不适用于新H/Q全局路径或新参数。

日期：2026-10-24（Asia/Singapore）。分支 `fix/full-reuse-hierarchy-migration`。这是源码/参数/RTL导出结构证据，**不是 RTL 数值或运行周期验收**。

当前 `hw/chisel_src/` 只有 full 四层实现及配置/生成工具，无 reuse 隔离目录、旧 PE/MN/K 源码或配置；Scala 与镜像 spec 共27对。来源 commit 与文件hash见 [full-reuse-source.json](https://github.com/Futuresxy/DP-Puzzel/blob/6522618cb78dac9bc2f64c11e00365e730435b95/hw/spec/full-reuse-source.json)，原工程只读文件指纹已重新核对一致。

| 检查 | 结果与范围 |
| --- | --- |
| Scala 编译 | 通过；27文件，Scala2.13.12、Chisel/plugin6.4.0 |
| CHIRRTL review | 5种配置通过：N1/2/3/4的W40，以及N1/W64；warnings-as-errors |
| 展开层级 | 每份检查PETile/MidGroup/PEGroup/SubPE为1/N/4N/16N |
| 非法配置 | N0/N5、W39/W65、非整数、未知字段、旧kind/pes共7类拒绝 |
| split RTL | N1与N3的W40配置通过firtool1.62.0；各12个去重module定义，一module一同名.sv |
| 导出来源与完整性 | 当前源码清单、RTL、files.f SHA-256一致；module映射到dp.pe/dp.core相应类与文件 |
| 物理层级 | N1为1/1/4/16；N3为1/3/12/48；两份均只有一份C解码、最终LZD和RoundPack通路 |
| 检查工具负例 | 内存模拟RTL字节损坏能被hash检查拒绝；在同步修改文件hash后删除一个MidGroup实例仍被层级检查拒绝。没有修改导出RTL |
| 文档与skill | 当前逐文件spec无缺失/孤立，活动本地链接检查；chisel-design skill校验通过 |
| SV 数值/周期 testbench | 未执行；待源码/接口合同审查后完成 |
| DC / power / characterization | 未执行；当前RTL不允许进入PPA |

最终源码清单 SHA-256：`acc2aa5b2f39f0ff3ba58acc36fd0fcf68adbfb934306853e01d18fdff57a7df`，覆盖27个Scala文件及build.sc/.mill-version。生成时尚未提交，manifest如实记录git_dirty=true及当时commit；本次提交/后续文档更新不会改变该源码指纹。

本地唯一 `hw/rtl/` 中保留的最终导出（生成文件不提交Git）：

- `PETile_H16Q32E64__full-09cf7b9f11c7__20261024T040823178559Z__acc2aa5b2f39`
- `PETile_H48Q96E192__full-3271efdd89ef__20261024T040826225681Z__acc2aa5b2f39`

两份均为 `state=generated / rtl_test=not_run / ppa_eligible=false`。同构module定义去重不改变实例数量，也不证明所有SubPE共用一个运行时乘法器。只有这两种配置执行了split RTL；W64与N2/N4仅有CHIRRTL结构证据。

复现（前四条在hw目录，最后两条在仓库根目录）：

```sh
mill -i pe.compile
mill -i pe.runMain dp.elaborate.Elaborate review
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/full_h16q32e64.json "full source review"
CHISEL_FIRTOOL_PATH=/path/to/firtool-1.62.0/bin mill -i pe.runMain dp.elaborate.Generate configs/full_h48q96e192.json "three MidGroup review"
python scripts/check_full_reuse_export.py PETile_H16Q32E64__full-09cf7b9f11c7__20261024T040823178559Z__acc2aa5b2f39
python scripts/check_full_reuse_export.py PETile_H48Q96E192__full-3271efdd89ef__20261024T040826225681Z__acc2aa5b2f39
```

本轮过渡导出的源码/目录已被替代，确认无test/PPA/DSE/论文引用后仅清理其src/files.f，保留superseded manifest/README及旧来源指纹。旧扁平方案的既有导出未触及，其历史记录不适用于当前full实现。
