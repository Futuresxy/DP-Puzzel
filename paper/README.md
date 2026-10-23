# DAC 2027 论文写作区

当前只准备可编译的匿名空白骨架，等待作者写作；没有论文结论、实验数字或虚构参考文献。

| 位置 | 职责 |
| --- | --- |
| main.tex | 论文入口，IEEEtran conference / 10pt |
| sections/ | 摘要、背景、方法、验证、实验、局限等分节正文 |
| figures/ | 图表成品和可编辑图源；记录数据/run 来源 |
| tables/ | LaTeX 表格及其数据来源 |
| references/references.bib | 经核验的引用条目，当前为空 |
| references/notes/ | 阅读笔记与证据摘录；原文大文件放忽略的 library/ |
| template/upstream/ | 未修改的 IEEEtran 类、conference 示例、BibTeX 样式和许可说明 |
| template/SOURCE.md | 模板来源、版本、hash 和获取方式 |
| submission/ | DAC 规则、披露记录、提交材料说明 |
| build/ | 被忽略的编译结果 |

在 paper 目录运行：

```bash
mkdir -p build
TEXINPUTS=./template/upstream//: latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex
```

当前参考文献为空，bibliography 调用暂时注释；写入真实引用后启用 main.tex 末尾的调用。最终检查正文 6 页和独立参考文献页的规则，当前空白骨架编译成功不等于符合最终投稿内容要求。

使用 agent 辅助润色时指定 [academic-humanizer](../.skill/academic-humanizer/SKILL.md)。它用于清晰表达并保留数据、符号和引用；使用从下一轮起可显式指向该文件。论文真实内容仍由作者审核。

本项目采用 DAC 官方要求的 IEEE 模板体系；不是声称存在单独的 DAC 2027 类文件。会议规则与时间见 [requirements.md](submission/requirements.md)。
