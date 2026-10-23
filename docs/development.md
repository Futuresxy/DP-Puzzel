# 开发、协作与归档流程

## 当前阶段

定义边界、职责、数据契约和工作流；不编写硬件、模型、构建或 EDA 脚本。按用户追加要求准备 paper 模板与写作 skill，不代写研究结果。现有 .codex/.agents 等保持不变，新项目 skill 统一放 .skill/<name>/SKILL.md。

## Git 与 PR

远程目标：git@github.com:Futuresxy/DP-Puzzel.git。

1. 开工检查工作区、分支和远程历史，保护未提交变更。
2. 新功能先建 feat/<topic> 分支；修复用 fix/，文档用 docs/，基础设施用 chore/。
3. 完成可审查批次，执行适用检查，更新 spec、接口和结果说明。
4. 检查 diff、待提交文件大小、敏感内容；显式 git add，commit 后推送工作分支。
5. 创建/更新 PR，说明问题、最终变化、验证、未执行检查与复现信息；未完成工作使用 draft PR。
6. 审查与必要检查完成后经 PR 合并，不绕过失败检查，不 force-push 主分支。

空仓库可建立仅含基础约定的 main 基线，主体由分支 PR 引入。有代码修改的每个工作日（Asia/Singapore）至少一次 commit + push；重大架构或关键数据更新形成可复现批次后及时同步。无变更不造空提交。

这是开发行为约定，不是已启用的定时任务。权限/网络/认证阻塞时分别报告本地提交、远程推送和 PR 状态。

## Git 保存核心内容

提交源码、SV testbench、spec、共享配置、skill、依赖版本/接入层、精简 profile、关键结果摘要及归档 URI/hash。paper 保存正文、BibTeX、必要图表源、模板及许可证和投稿规则来源。

缓存、完整 RTL 导出、大波形、EDA 全报告、原始 trace、大型扫描输出、论文编译文件、第三方运行源码、PDK/许可证/密钥保留本地或受控归档。单文件超过 5 MiB 默认不提交；必要时先定义外部归档或 LFS 策略。gitignore 不会移除已跟踪文件，仍需审查 staged 清单。

## 清理、skill 与依赖

设计 RTL 保留唯一来源；衍生 netlist 和报告按 run 管理并绑定来源。失败后清理不再使用的生成文件，保留错误摘要、最小复现和引用关系。禁止无差别 git clean -xfd，禁止删除 ref_work、.skill、.codex 或用户文件。

所有新 skill 放 .skill；共享流程复用未来 scripts 入口。CACTI 等在首次使用前按固定版本拉取到 .deps，项目只存版本清单、adapter 和必要补丁。用户指定保留的论文模板和写作 skill 是有许可证的小型开发资产，不属于把建模依赖源码树混入实现。
