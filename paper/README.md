# DAC 2027 论文

## 当前中文审核稿：DSE 主线（2026-11-11）

[main.tex](main.tex) 是当前中文入口，按六章组织：引言、背景与动机、组合式点积微架构、硬件成本表征、面积约束 DSE、结论。第三章已并入 E/QE 专用 Group 与 DP 内增配；原有两种扩展方式的比较从正文撤下。主线是“可实现 DP → 同工况成本 → 整核部署 → 工作量组成 → 配比选择”。章节映射、证据边界和下一步实验见 [research_plan.md](research_plan.md)。

本轮仅修改中文。英文单文件 [dp_puzzle.tex](dp_puzzle.tex) 保留上一轮七章版本，待用户确认后同步。当前中英文的章节、公式、表格和图源存在有意差异；`Makefile.en check` 会报告这些差异，不能当作已通过一致性检查。不得用旧英文内容覆盖本轮中文结构。

```bash
make -C paper pdf                    # 中文：paper/build/main.pdf
make -C paper watch                  # 中文保存后持续编译
make -C paper -f Makefile.en          # 上一轮英文：paper/build/dp_puzzle.pdf
```

硬件成本继续引用现有 N12、0.7 V、85°C、1 GHz 测量，未重新执行 EDA。四种配比面积及逐精度功耗图为 `figures/ratio4_{area,power}.png`，功耗柱高为实测 mW，所有倍率统一以 1:2:4 的 BF16 功耗为基线。生成数据与 hash 见 [data/DP_area_power/README.md](data/DP_area_power/README.md)。旧六 DP 图、测量数据和历史对比依赖保留。

当前负载来自固定配置和模型特定规则；新增通用提取流程、V3.2/R1 及两个实际专家量化版本的核验列为后续实验。正文中的专家 W4A4 是迁移场景，NVFP4 能耗暂用 MXFP4 活动功耗代理。`data/results` 是当前硬件结果；`data/expected` 保持历史工作量回归，不用于替换现行时间/能耗。

定点记号采用 `QI.F` / `UQI.F`，整数位数 I 不含符号位，位宽分别为 `1+I+F` / `I+F`；精度类别 Q 与定点 Q 格式由上下文区分。Lane 和 DP 的对齐窗口均为无符号幅值，基线分别为 28 和 39 位。论文正文不使用代码版本与 run ID。

架构图只使用作者现有图稿；需要补画的内容列在研究计划中。本轮仅用既有绘图代码和测量数据生成四配比数据图。中文保留 10 pt 工作稿排版，本轮编译为正文 6 页、参考文献 1 页；未发现未解析引用或溢出。英文尚未同步，需单独复核其最终篇幅。

## 保存后预览 PDF

**工作区范围：** 若 VS Code 打开的是上一级 `workspace/`，不会加载嵌套的 `DP-Puzzel/.vscode` 设置。推荐通过「文件 → 从文件打开工作区」打开 `paper/paper.code-workspace`；直接打开 `paper/` 也已配置。`main.tex` 首行的 `% !TeX program = latexmk` 让默认编译按钮使用本地 `.latexmkrc` 中的 XeLaTeX，而不采用插件默认的 `latexmk -pdf`。已有的错误不是字体缺失，而是 pdfLaTeX 不支持 `fontspec`。

切换配置后可执行 `Developer: Reload Window`。若手动选过旧 recipe，执行 `LaTeX Workshop: Build with recipe`，选择 `DP-Puzzel (XeLaTeX)`；正确日志应出现 `Running 'xelatex ...'`。不要用 `-f` 忽略引擎错误。

本机 VS Code 项目已配置 LaTeX Workshop；也可使用「文件 → 从文件打开工作区」打开 [paper.code-workspace](paper.code-workspace)，直接进入论文写作区。

1. 打开 `main.tex`，按 `Ctrl+Alt+B` 首次编译。
2. 按 `Ctrl+Alt+V`，在右侧打开内置 PDF 预览。
3. 编辑 `sections/*.tex` 后按 `Ctrl+S`；插件自动编译完整论文，成功后刷新 PDF。

各章节首行的 `% !TeX root = ../main.tex` 指定完整论文入口。编译使用 XeLaTeX 与现有 `.latexmkrc`，输出始终为 `build/main.pdf`；`Ctrl+Alt+J` 可从源码光标跳转到 PDF 对应位置。若编译失败，预览保留上一次成功结果，可在 LaTeX Workshop 输出面板查看错误。

不使用插件自动编译时，可在 `paper/` 运行 `make watch` 持续监视文件，按 `Ctrl+C` 停止；不必同时运行两套自动编译。`make` 仍可用于单次编译，`make cost-figures` 用于更新面积/功耗 PNG。

## 编译与重绘

需要 XeLaTeX、latexmk、BibTeX（TeX Live 的 xeCJK、IEEEtran、subfig/caption 相关依赖），以及 Python 3、NumPy、Matplotlib。正文采用 TeX Gyre 和 Fandol 字体；图中文字优先 Arial。IEEE 模板随目录保留，来源见 [template/SOURCE.md](template/SOURCE.md)。

```bash
cd paper
python3 -m pip install -r requirements.txt  # 缺少依赖时执行
make                    # 仅编译正文，输出 build/main.pdf
make reproduce          # 重算部署、负载、三角分区、两张图和三张表
# make diagrams         # 历史示意图入口；本轮不调用，架构图由作者维护
make cost-figures       # 按可编辑 CSV 重绘 select8 面积/功耗和 H16Q32E64 面积占比
make check              # 保持历史工作量不变，核验当前测量输入、部署与时间/能耗
make test               # 临时目录内验证修改参数后的重算
```

`make` 不会自动覆盖图表。可先运行 `make reproduce` 检查新结果，再 `make` 更新 PDF。编译和分析均不依赖原工程、网络或 GPU。

### 负载配比分区图

第六节使用 `figures/k4_n12_prefill_comparison.png`，左右分别为整数核心部署下的最小计算延迟与最小 DP 计算能耗。图内标注四种配比及其最优区域的几何面积占比，并提供 H/Q/E 百分比刻度、20%/30%/50% 读数示例和三模型×两种专家量化映射的图例。原区域表不再单独排入正文；连续/整数部署及能耗的数值仍保留于 `tables/region_table.tex` 和 `data/results/regions.json`。

组合图将读数示例置于两三角图之间的上方空白处，底部仅保留两行量化方案、三列模型的紧凑图例。配比标签不加底色；区域百分比、轨迹方向和实心终点的解释放在论文图注。

仅重绘、不重算负载或覆盖结果数据：

```bash
python3 scripts/plot_triangles.py  # 使用已安装 requirements.txt 的 Python 环境
```

脚本读取 `data/results/{regions.json,prefill_points.csv,nvfp4_prefill_points.csv}`，仅输出组合图及两个独立面板的 400 dpi PNG，字体与 `data/H16Q32E64_area/plot_area_comparison.py` 使用相同的衬线字体配置；输入哈希、实际字体和区域百分比记录于 `figures/k4_n12_prefill_plot_manifest.json`。完整 `reproduce.py` 使用同一绘图入口。NVFP4 能耗仍使用 MXFP4 活动功耗代理；读数示例不是模型负载点。

## 修改哪些数据

| 文件 | 修改内容 |
| --- | --- |
| [data/inputs/experiment.json](data/inputs/experiment.json) | 基准核数、阵列 M/N、基准阵列面积占比、外围增长系数、batch、上下文序列、三角扫描密度 |
| [data/inputs/hardware_n12.json](data/inputs/hardware_n12.json) | 四配比的单 DP 面积、各格式 MAC/cycle、频率和活动功耗；保留测量批次与原始来源 hash |
| `data/inputs/models/<模型>/inference/config.json` | 三模型结构、专家数量、隐藏维度、压缩比例等；改变后代表对应的结构分析场景 |
| [scripts/costs.py](scripts/costs.py) | 执行精度映射、固定外围部署和时间/能耗公式 |
| [scripts/workloads.py](scripts/workloads.py)、[scripts/deepseek_v41.py](scripts/deepseek_v41.py) | V4/V4.1 的有效 GEMM 工作量、注意力与 CED 计算规则 |
| [scripts/plot_triangles.py](scripts/plot_triangles.py) | 配色、字号、标记和轨迹；标题及图注由 LaTeX 管理 |

例如把 `baseline_cores` 改为 32 后，默认硬件下部署核数变为 32/30/29/26。修改面积和功耗应同时更新来源信息；自行设定的数据属于敏感性分析，不能作为新的硬件测量。

独立试验可以不覆盖论文图表：

```bash
python3 scripts/reproduce.py --config data/inputs/experiment.json --output /tmp/dp-paper-trial
```

`--config` 中的 `hardware` 相对该配置文件解析；模型配置固定从本目录 `data/inputs/models/` 读取。当前入口针对四种既定配比和三个模型，不是任意设计空间生成器。

**重绘更新数值表格和图形，不自动改写正文结论。** 修改参数后需同步审核正文中的面积、核数、百分比、轨迹端点和图注中的上下文范围。`make check` 核对默认测量输入，并检查历史工作量保持不变；自定义参数用独立输出目录和 `make test` 验证，不要求新硬件结果匹配历史值。

## 建模口径

设每阵列包含 `m*n` 个 DP，单 DP 面积为 `a_j`，基准阵列面积占比为 `alpha`，基准核数为 `N0`：

```text
A_T,j = m*n*a_j
A_O,0 = (1/alpha - 1)*A_T,0
A_budget = N0*A_T,0/alpha
A_core,j = A_T,j + A_O,0 + growth*(A_T,j - A_T,0)
n_j = floor(A_budget/A_core,j)
C_j,f = n_j*m*n*2*k_j,f*frequency
P_j,f = n_j*m*n*p_j,f
T_j = sum_f(F_f/C_j,f)
E_j = sum_f(F_f*P_j,f/C_j,f)
```

默认 `growth=0`，固定每个核心的外围面积；预算为等效核心池面积，并非商业芯片实测 die 面积。固定频率、充分利用的模型中，增加实例同时增加功耗和吞吐，所以实例数在单位工作能耗中抵消。外围面积不能按比例换算外围功耗。

三角坐标是 H/Q/E 的 **FLOP 占比**，不是执行时间占比。吞吐分区比较总时间；能耗分区比较总 DP 能耗。MX/NV 两类 FP4 使用相同峰值，数据结构保留独立功耗字段。当前 NV 功耗取 MX 代理，因此图中编码选择区域完全重合，不能据此声称实际 NV/MX 能耗相同。换入独立 NV 功耗后，绘图支持标出随编码混合比例改变的区域。

两类轨迹均由配置和计算公式重算：

- `reference_work`：BF16 归 H、FP8/W4A8 专家归 Q、原生 MXFP4 索引归 E。
- `nvfp4_experts`：仅把路由专家 gate/up/down 三个 GEMM 转为 NVFP4 W4A4，其余工作量不变。

三模型均统计纯文本冷 prefill 的有效 GEMM；V4.1 包含 CED 缓存构建与有限窗口重放。FP32 单独统计并排除出 H/Q/E 分母。这是由已固定版本来源导出的计算需求，不是现场运行 vLLM 的 trace，不代表量化精度验证或端到端延迟实测。

当前 12 nm 功耗来自 Qwen3-8B 第一层 MLP down-projection 的连续活动窗口，用于 DeepSeek 工作量时属于活动代理。H 以 BF16 代表，NVFP4 暂用 MXFP4 功耗；结果不包含外设、存储、通信及停顿能耗。本次写作复用已有硬件测量，未重新运行 EDA 或模型推理。

更新输入后可运行：

```bash
python3 scripts/import_dp_measurements.py
make check
make test
```

导入脚本读取仓库中固定批次的六架构 CSV，并保留来源 hash、测量工况和代理说明。若要更新测量批次，应修改导入来源并核验测量条件。

## 目录与结果

- `sections/`：摘要及六章正文；微架构与增配为 `03_architecture.tex`，成本表征为 `04_evaluation.tex`，DSE 为 `05_dse.tex`，结论为 `06_conclusion.tex`。
- `references/references.bib`：文献和 BibTeX 格式控制条目；五项 DP 相关工作的比较条件另存于 notes。
- `figures/`：正文插图；四张原有架构/格式图保留 PNG，其余提供绘图代码。
- `tables/`：固定面积部署、MXFP4 区域占比及 prefill 端点三张表，由脚本生成。其余表格在章节内维护。
- `data/inputs/`：可修改的实验输入。
- `data/results/`：重新计算的核数/算力/功耗 CSV、两类模型点与逐配比结果、工作量账本、扫描结果、精确区域及输入 hash。由 Git 忽略，随时重建。
- `data/expected/`：历史论文的五份精简基准，不参与新结果计算；当前回归核对其中不应随硬件变化的工作量字段。
- `data/evidence/`：输入来源、版本、校验和及其他正文表格的紧凑证据；原始路径仅用于溯源，不是运行依赖。
- `template/`、`submission/`：保留目标工程原有模板来源、投稿要求和 AI 使用记录。

默认面积预算为 496.59255257088006 mm²，四配比核心数为 36/34/32/29，两类映射共 42 个工作量点、168 个配比评估。1:2:6 的延迟/能耗最优区域分别占 7.94%/2.84%，旧稿的“无优势区域”结论不再适用。模型输出为计算服务时间和 DP 活动能耗，不能表述成整芯片实测。

## Select8 成本与 DP 面积占比图

运行 `make cost-figures` 可重建历史 Select8 面积与功耗图；当前正文不引用这些图。[Select8 数据说明](data/DP_area_power/README.md) · [PETile 参考图](figures/H16Q32E64_area_pie.png)

新版六种 DP 的七类面积与总功耗分别保存在两张 CSV。运行 `make dp-share-figures` 重绘六张面积图和六张总功耗图。[面积](data/H16Q32E64_area/README.md) · [总功耗](data/H16Q32E64_power/README.md)


## 图表排版约定

图片使用单栏 `figure`，宽度不超过 `\columnwidth`。组合图用 `\subfloat` 编号及命名，图内不嵌入图片标题；模型、符号、颜色、子图含义和比较条件在图下 `caption` 说明。当前两张负载三角图上下排在同一栏，使用已有 PNG 和绘图代码。架构图保留作者素材与空缺图位，不自动绘制。

相关工作比较使用原生 LaTeX 双表：`tables/related_features.tex` 是精度/功能勾选矩阵；`tables/related_ppa.tex` 按工作分列、按精度分行列出实现条件和效率。两表包含五项相关工作及本设计，采用跨栏表格保持文字可读性，不作为图片插入。数值来源与换算见 `references/notes/dp_comparison.md`。
