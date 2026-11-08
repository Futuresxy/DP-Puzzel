# DAC 2027 论文

后续写作入口为 `main.tex`。引言与背景以 DP-puzzle-SW/paper 版本为主，统一到四配比研究范围；架构、评估、结论和实验图表迁自 DAC2027 当前稿，按章节拆分；研究范围为四种配比的 DP 成本、K/N 实现差异、固定面积下的负载选择。文献仅保留正文引用的条目，图片仅保留实际使用的七张。旧稿、扩展配比扫描、整份文献库和 EDA 大型产物不在此目录。

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

需要 XeLaTeX、latexmk、BibTeX（TeX Live 的 xeCJK、IEEEtran 相关依赖），以及 Python 3、NumPy、Matplotlib。正文采用 TeX Gyre 和 Fandol 字体；图中文字优先 Arial。IEEE 模板随目录保留，来源见 [template/SOURCE.md](template/SOURCE.md)。

```bash
cd paper
python3 -m pip install -r requirements.txt  # 缺少依赖时执行
make                    # 仅编译正文，输出 build/main.pdf
make reproduce          # 重算部署、负载、三角分区、两张图和两张表
make diagrams           # 重绘 DP 背景和 K/N 组织示意图
make cost-figures       # 按可编辑 CSV 重绘 select8 面积/功耗和 H16Q32E64 面积占比
make check              # 重算默认实验，与迁移前的论文结果逐字段比较
make test               # 临时目录内验证修改参数后的重算
```

`make` 不会自动覆盖图表。可先运行 `make reproduce` 检查新结果，再 `make` 更新 PDF。编译和分析均不依赖原工程、网络或 GPU。

## 修改哪些数据

| 文件 | 修改内容 |
| --- | --- |
| [data/inputs/experiment.json](data/inputs/experiment.json) | 基准核数、阵列 M/N、基准阵列面积占比、外围增长系数、batch、上下文序列、三角扫描密度 |
| [data/inputs/hardware_n12.json](data/inputs/hardware_n12.json) | 四配比的单 DP 面积、各格式 MAC/cycle、频率和活动功耗；保留测量批次与原始来源 hash |
| `data/inputs/models/<模型>/inference/config.json` | 三模型结构、专家数量、隐藏维度、压缩比例等；改变后代表对应的结构分析场景 |
| [scripts/costs.py](scripts/costs.py) | 执行精度映射、固定外围部署和时间/能耗公式 |
| [scripts/workloads.py](scripts/workloads.py)、[scripts/deepseek_v41.py](scripts/deepseek_v41.py) | V4/V4.1 的有效 GEMM 工作量、注意力与 CED 计算规则 |
| [scripts/plot_triangles.py](scripts/plot_triangles.py) | 配色、字号、标记和轨迹；标题及图注由 LaTeX 管理 |

例如把 `baseline_cores` 改为 32 后，默认硬件下部署核数变为 32/29/28/26。修改面积和功耗应同时更新来源信息；自行设定的数据属于敏感性分析，不能作为新的硬件测量。

独立试验可以不覆盖论文图表：

```bash
python3 scripts/reproduce.py --config data/inputs/experiment.json --output /tmp/dp-paper-trial
```

`--config` 中的 `hardware` 相对该配置文件解析；模型配置固定从本目录 `data/inputs/models/` 读取。当前入口针对四种既定配比和三个模型，不是任意设计空间生成器。

**重绘更新数值表格和图形，不自动改写正文结论。** 修改参数后需同步审核正文中的面积、核数、百分比、轨迹端点和图注中的上下文范围。`make check` 只适用于未改变默认输入时的迁移回归；新参数不应被迫匹配旧结果。

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

三角坐标是 H/Q/E 的 **FLOP 占比**，不是执行时间占比。吞吐分区比较总时间；能耗分区比较总 DP 能耗。MX/NV 两类 FP4 使用相同峰值但分别计功耗，能耗图实色部分在两种编码之间保持相同优胜配比，斜线部分取决于编码混合比例。

两类轨迹均由配置和计算公式重算：

- `reference_work`：BF16 归 H、FP8/W4A8 专家归 Q、原生 MXFP4 索引归 E。
- `nvfp4_experts`：仅把路由专家 gate/up/down 三个 GEMM 转为 NVFP4 W4A4，其余工作量不变。

三模型均统计纯文本冷 prefill 的有效 GEMM；V4.1 包含 CED 缓存构建与有限窗口重放。FP32 单独统计并排除出 H/Q/E 分母。这是由已固定版本来源导出的计算需求，不是现场运行 vLLM 的 trace，不代表量化精度验证或端到端延迟实测。

12 nm 功耗是旧论文所用 Qwen3-0.6B 活动下的 DP 表征；22 nm 的 RQ1/RQ2 数据另存于 `data/evidence/n22/`。**这些数据不等于本仓库当前 `src/verilog` 新版 RTL 的 PPA。** 迁移没有重跑综合、功耗或推理测量。

## 目录与结果

- `sections/`：摘要、引言、背景、架构、评估、结论；带宽和固定面积评估分别维护。
- `references/references.bib`：正文所需 35 条文献及 1 个 BibTeX 格式控制条目。
- `figures/`：正文插图；三张原有架构/格式图保留 PNG，其余提供绘图代码。
- `tables/`：固定面积部署和 prefill 端点表，由脚本生成。其余 RQ1/RQ2 表仍在正文内维护。
- `data/inputs/`：可修改的实验输入。
- `data/results/`：重新计算的核数/算力/功耗 CSV、两类模型点与逐配比结果、工作量账本、扫描结果、精确区域及输入 hash。由 Git 忽略，随时重建。
- `data/expected/`：迁移前论文的五份精简基准，用于数值回归，不参与新结果计算。
- `data/evidence/`：输入来源、版本、校验和及其他正文表格的紧凑证据；原始路径仅用于溯源，不是运行依赖。
- `template/`、`submission/`：保留目标工程原有模板来源、投稿要求和 AI 使用记录。

默认结果：405.5663803392 mm²，核心数 36/33/32/29，两类映射共 42 个点；迁移回归核对 1,843 个字段。论文保留六页正文与一页参考文献。作者仍需审核论文论断与最终投稿材料。

## Select8 成本与 DP 面积占比图

在 [data/DP_area_power/](data/DP_area_power/README.md) 修改 `selected8_area.csv` 的面积、`selected8_power.csv` 的动态/静态功耗；在 [data/H16Q32E64_area/](data/H16Q32E64_area/README.md) 修改 `area_data.csv` 的 `category` / `total_um2`。运行 `make cost-figures` 后，三个 PNG 更新到 `figures/`，总功耗、基线倍率、分类面积占比自动重算。该入口不含 selected14 或 21 配置合并；当前正文及图片引用保持不变，后续可引用这些图。
