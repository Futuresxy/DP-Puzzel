# 工艺代理归一化

这是论文的解析比较，不是工艺库移植或新EDA测量。用DeepScaleTool的14 nm节点代理12 nm；已为12 nm的数据保持不变。面积效率包含延迟对应的频率缩放，能效按能量缩放；不额外缩放电压。

- `python3 calculate.py`：复算原有Ten-Four四配置比较，保留固定频率的面积缩放敏感性结果。
- `python3 normalize_table.py`：从`table_inputs.json`和本项目功耗CSV计算全表原值及12 nm代理值，表中仅显示代理值；生成`table_efficiencies.csv/json`，更新`paper/tables/related_ppa.tex`的生成标记区。
- `dependencies/deepscaletool.json`：官方电子表格固定版本、下载URL、许可与hash。数据源在忽略目录`.deps/`，不提交第三方宏。所用系数已逐项比对原表current/target查表分支，未执行宏。

7→14使用已采用的14→7三位显示系数的倒数；22/28→14使用官方查表比率并保留三位显示精度。效率计算保留输入精度，最后显示三位小数。JSON记录换算因子和输入hash；缺失效率不补零、不从不同统计范围的功耗推断。

详细文献口径和复核记录见`paper/references/notes/dp_comparison.md`。
