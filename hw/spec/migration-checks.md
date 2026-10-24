# 迁移结构检查记录

> 历史扁平方案记录。本轮当前基线为 [full 四层复用迁移](full-reuse-migration.md)，此处接口与证据不适用于该基线。

记录日期：2026-10-24（Asia/Singapore）。这是源码/参数/生成流程检查，不是 RTL 数值验收。

| 项目 | 结果 | 范围 |
| --- | --- | --- |
| Scala 编译 | 通过 | 13 个 Scala 文件，Scala/plugin 2.13.12/6.4.0 |
| CHIRRTL review | 24 个配置通过 | 八种 PE 及 MNPE、KPE 1–4 个 Full、两个异构布局、两个 W64 边界；warnings-as-errors |
| 非法配置 | 拒绝 | kind=mn 配两个 PE，在 elaboration 前报错 |
| Scala/spec 映射 | 13 对通过 | config/common/pe/core/elaborate 镜像；无缺失或遗留旧路径 |
| skill 校验 | 通过 | chisel-design frontmatter/名称 |
| split RTL 生成 | 两个配置通过 | firtool 1.62.0，实际 lowering 和一 module 一文件 |
| 导出完整性 | 通过 | 源文件、RTL、files.f SHA-256 与模块映射一致 |
| SV 数值/周期 testbench | 未执行 | 待用户源码审查后完善 |
| DC / 功耗 / characterization | 未执行 | 禁止基于当前结果发布 PPA |

生成时源码清单 SHA-256：`19c620f62247fc43eb6da381073b80bfb4e868b2e7cbddd95f4abf9b027d113a`。源码指纹覆盖 Scala 文件、build.sc、.mill-version；文档不改变该值。生成时工作区尚未提交，因此 manifest 如实标注 git_dirty=true；后续提交不改变已生成 RTL 的来源指纹。

保留在本地唯一 hw/rtl 中的两个导出（不提交生成文件）：

- `MN_PE_H0Q0E32__mn-4abb11c9efb4__20261023T171202231734Z__19c620f62247`：3 个 module，约 197 KB。
- `K_PE_H16Q64E160__k-832f089dcf64__20261023T171339952238Z__19c620f62247`：6 个 module，约 1.73 MB。

两份 manifest 均为 `state=generated`、`rtl_test=not_run`、`ppa_eligible=false`。调试导出入口产生的失败批次已自动删除 src/files.f，仅保留最小 failed manifest/README，不把失效 RTL 留给后续调用。

复现命令见 [源码导航](https://github.com/Futuresxy/DP-Puzzel/blob/09b6657f26a0bf12aadc0051614db023a96850fa/hw/spec/../chisel_src/README.md) 和 [生成规格](https://github.com/Futuresxy/DP-Puzzel/blob/09b6657f26a0bf12aadc0051614db023a96850fa/hw/spec/elaborate/Generate.md)。本地检查日志位于忽略的 `.cache/pe-elaborate-review.log` 与 `.cache/pe-invalid-config-check.log`。实际导出状态不能因本记录写了“检查通过”而升级为 RTL 验证通过。
