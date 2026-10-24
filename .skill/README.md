# 项目技能预留

本项目所有技能统一存放于此，例如 `.skill/dc-synthesis/SKILL.md`、`.skill/power-analysis/SKILL.md`。辅助脚本和参考资料放在对应技能子目录；技能引用根目录 AGENTS.md 和公共仓库脚本，避免复制另一套实现。

已安装用户指定的 [academic-humanizer](academic-humanizer/SKILL.md)，来源为 AIScientists-Dev/academic-humanizer，固定版本见 [安装记录](academic-humanizer/INSTALLATION.md)。论文写作时由根目录 AGENTS.md 引导读取，无需把技能复制到其他位置。

已定义 [power-analysis](power-analysis/SKILL.md)：使用 RTL 测试真实数据、门级 SAIF 和 DC/Power Compiler，衔接明确综合 run，N22 优先、N12 显式备选；包含任务/稳态窗口、长度收敛与活动验收。当前是流程与计划配置，尚无功耗执行入口或测量结果。

已有 `.codex/`、`.agents/` 等设置保持不变。此目录名是项目统一存放约定；不假定应用会自动扫描任意自定义目录，下轮可显式指定技能文件使用。
