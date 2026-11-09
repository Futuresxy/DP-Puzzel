# 当前六种 DP 综合结果

当前入口：[v1.9比较批次面积与时序](v19_six_dp_20261110.md)、[机器索引](v19_six_dp_20261110.json)。dp_top为v1.8电气修复基线，三个混合顶层和Q32E64为v1.9，E64保持原专用E设计及其已验收网表；均为N12 TT/0.7V/85°C、1GHz、L8/II=1、LOCAL28/GLOBAL40、ICG开启。

[旧门控六架构面积与时序](latest_six_dp.md)及其[JSON](latest_six_dp.json)保持原内容，作为历史对照。[固定格式直接打包](fixed_unpack_20261109.md)是此前独立实验；不能替代本轮绑定的新RTL、DC和功耗证据。

runs中保留本轮最终结果、必要修复祖先及全部旧功耗对照依赖。原Q32E64的hold失败、baseline原最大电容违例和最终修复结果分别保留。全部现用及历史比较引用的网表/DDC/SDC、工具配置、报告、冻结快照和回归证据不参与普通滚动删除。

功耗以独立的[本轮六架构报告](../../power/records/v19_six_architectures_20261110.md)为准；[旧门控功耗](../../power/records/current_six_precision_gated.md)继续保留。DC流程中的power_ready=false属于综合阶段占位，具体负载验收由绑定网表与活动的功耗报告给出。

新索引显式固定六个run、原始验证ID与hash；只发布通过全部验收的综合结果。当前源码与冻结输入分别核验，不能用旧报告替代新源码验证，也不能按目录时间自动替换正式比较输入。

本轮[清理回执](../maintenance/precision_gated_six_cleanup_20261108.json)记录无引用测试/快照的清理及保留依赖；已退役快照只保留manifest/README等失效说明。全部旧功耗对照数据和现存DC比较摘要继续保留。此前清理的记录见[历史维护回执](../maintenance/latest_six_cleanup_20261108.json)；已删除的大产物不能从Git恢复。
