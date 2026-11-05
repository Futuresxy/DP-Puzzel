# 项目技能

本项目所有技能统一存放于此，例如 `.skill/dc-synthesis/SKILL.md`、`.skill/power-analysis/SKILL.md`。辅助脚本和参考资料放在对应技能子目录；技能引用根目录 AGENTS.md 和公共仓库脚本，避免复制另一套实现。

已安装用户指定的 [academic-humanizer](academic-humanizer/SKILL.md)，来源为 AIScientists-Dev/academic-humanizer，固定版本见 [安装记录](academic-humanizer/INSTALLATION.md)。论文写作时由根目录 AGENTS.md 引导读取，无需把技能复制到其他位置。

硬件开发与审查使用 [chisel-design](chisel-design/SKILL.md)：维护 PE/MN-PE/K-PE 架构及 Scala/spec 一一对应，明确位宽、scale、资源复用和流水依据。

单 DP 真实负载功耗的方案和测量使用 [power-analysis](power-analysis/SKILL.md)，包括 VCS 原生门级 SAIF、Power Compiler 注释验收和精度比较口径。

已有 `.codex/`、`.agents/` 等设置保持不变。此目录名是项目统一存放约定；不假定应用会自动扫描任意自定义目录，下轮可显式指定技能文件使用。
