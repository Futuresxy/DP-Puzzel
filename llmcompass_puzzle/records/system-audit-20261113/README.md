# 系统资源机会成本与功率准入接口（2026-11-13）

本批次实际调用固定版 LLMCompass 面积模型，并使用同一 N12→7nm DP 工艺代理；完成27个配比/vector组合的同面积资源上限计算，增加量化工作量和窗口功率准入接口。10项集成/合同测试通过。尚未运行完整 DeepSeek 时序，也没有已校准的整芯片功率排名。

## 条件与复现

面积预算826.763555 mm²；1GHz、每SM四个4×4 DP，保持SRAM/HBM/L2和原SM外围模型。物理SM以8为一组、最多256个；保持启用比例108/128并向下取整。安装最多核心不是性能/能耗最优性的证明。vector资源档同时改变ALU、issue和RF端口，工艺代理与外围增量假设同S1。

```bash
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.system_audit \
  --output llmcompass_puzzle/runs/my-system-audit
llmcompass_puzzle/.venv/bin/python -W ignore::ResourceWarning \
  -m unittest discover -s llmcompass_puzzle/tests -v
```

已保留运行目录为 `llmcompass_puzzle/runs/system-audit-20261113-v4`。输入/源码/输出SHA-256与测试记录见 [manifest](manifest.json)、[evidence](evidence.json) 和 [tests](tests.txt)。

## 三项有量化依据的系统观察

1. **Tensor本体不是当前代理面积的大头。** 在1:2:4、128物理/108启用SM的参考组织中，Tensor占模型总面积2.25%，RF占24.72%，vector ALU占6.87%，L2占14.03%，SM SRAM占8.03%。RF是共享资源，并非全归vector。这里只是本模型分项和同BF16峰值组织，不能外推成实际A100实测比例。它提示后续搜索必须计入存储和外围成本。
2. **每SM的vector翻倍，不等于芯片vector翻倍。** 同预算下1:2:4的安装上限从128降至104个SM，启用数从108降至87；总vector峰值55.296→89.088 TFLOP/s（+61.11%），BF16矩阵峰值221.184→178.176 TFLOP/s（−19.44%）。这个机会成本能否换来延时收益，取决于Norm、量化、Softmax等实际占比。
3. **同FP4能力的更宽FP8配置也有系统代价。** 原档vector、同预算下，1:2:16能启用108 SM，1:8:16为101 SM。FP4芯片峰值3538.944→3309.568 TFLOP/s（−6.48%），同时其FP4模式全活跃DP动态功率代理116.365→144.142W（+23.87%）。后者并非全面更好；只有FP8阶段收益足够时才可能补偿。此功率仅是DP活动/工艺代理，不含非DP和泄漏，不能作为整芯片功率或实际模型能耗结论。

附加面积探针：按上游成本模型多一个物理HBM channel增加16.190 mm²；物理L2从48增至96MiB增加113.706 mm²。探针只改物理面积字段，未据此声称带宽、时延或容量已经改变；完整资源组合还需同步启用资源、功率和映射。

## 图与数据

[矢量PDF](../../../paper/figures/llmcompass_system_resource_tradeoff.pdf) 展示观察2：蓝色为matrix、斜线橙色为vector，全芯片峰值分别按原档vector下的对应峰值归一化。SM标注为启用数量。图不表示推理加速比。矩阵在固定1:2:4配比下各精度的相对变化相同，绘图取BF16。

```bash
# 绘图环境独立于CPU模型环境，使用 requirements-figures.txt 固定版本。
python -m llmcompass_puzzle.resource_figure \
  --run llmcompass_puzzle/runs/my-system-audit \
  --pdf paper/figures/my-system-resource-tradeoff.pdf \
  --evidence llmcompass_puzzle/runs/my-system-audit/figure.json
```

本次使用已存在的绘图环境，Matplotlib 3.11.2；图的输入hash、脚本/样式hash和PDF hash见 [figure.json](figure.json)。PDF为单页约244×166 pt，嵌入STIXGeneral字体，无位图；已检查文本、字体和渲染预览。LaTeX图注见 [figure_caption.tex](figure_caption.tex)。

## 量化与功率边界

`contract_examples.json` 中系数是明确的人工代数示例，仅验证接口机制，不用于以上芯片候选的功率排名。示例展示：融合省中间读写但不免除量化运算；某活动窗口70W、随后空闲，整段平均仅16W，仍不能通过60W窗口约束。真正非DP功率模板中的系数保持null。

下一步要把每个精度计划的完整转换路径与DeepSeek算子图接入：尤其W4A8→W4A4中已是W4的权重不会再次减半HBM流量，省下的展开应计入。以完整面积/容量/带宽约束下的时序为基础，按重叠窗口聚合matrix/vector/存储功率，枚举可行运行并发后重新排名。详见 [系统参数合同](../../SYSTEM_PARAMETERS.md)。
