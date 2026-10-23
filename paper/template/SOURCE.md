# 模板来源与版本

DAC 2027 官方投稿页面要求使用 IEEE conference 模板体系：[会议要求](https://dac.com/2027/program/research-manuscript-submissions)。没有假设另有 DAC 专用 class。

IEEE 官方模板下载地址返回空响应，故使用维护者发布到 [CTAN 的 IEEEtran 包](https://ctan.org/pkg/ieeetran)，版本 1.8b，许可证 LPPL 1.3。当前保留 conference 示例、class、BibTeX style 及原 README/许可说明；所有上游文件保持未修改。

- 获取地址：https://mirrors.ctan.org/macros/latex/contrib/IEEEtran.zip
- 获取时间：本轮 2026-10-23/24（Asia/Singapore）项目准备会话。
- 原始压缩包 SHA-256：e0cd4f5afbd42c8076092280e72b3e0a5111efe501d35de9f715cfb8da313cb4
- 原始包保留在忽略的 .cache/；使用下列核心文件重建写作环境。

| 上游文件（相对 upstream/） | SHA-256 |
| --- | --- |
| IEEEtran.cls | da751920a317ed318b7b5cd7fa585a6cc7d28502d457856382e9be24b10a3bd7 |
| bare_conf.tex | cc4fa258aa90115ad6afbd8ca5555f448880b29a971398bf1a20ee5f240b45f7 |
| README | cc2de809d6e86ab95cd4e88d97b41cb81dd96cf224e6445474aeb7419f4a0462 |
| bibtex/IEEEtran.bst | 314f0ece704568faf827011bac498650691b2b5ee06320720830e782416d5a5f |
| bibtex/README | 797417f3c4f37349f24869ceaf015fac36d4d147262d17b2ce50b36f32e806a7 |

paper/main.tex 是项目写作入口；upstream/bare_conf.tex 是未修改示例，不将示例中的作者/引用自动带入论文。不得修改 class 来挤压版面。将来会议更新要求时重新核验并记录变化。
