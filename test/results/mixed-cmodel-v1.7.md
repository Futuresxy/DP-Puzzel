# 混合 DP CModel 第一阶段：v1.7

基线 e298d9e，分支 feat/dp-verilog-v14。已实现 QE 前端及三个混合配置，默认28/40、L8/II=1；原 multi/E 算术与测试数据保持兼容。此阶段只验证CModel，未运行新RTL或DC。

| 配置 | 固定向量 | 数学 max_ulp | 新增 Q/E max_ulp | 超过4ULP |
| --- | ---: | ---: | ---: | ---: |
| t8h16q32e96 | 10747 | 3 | 1 | 0 |
| t8h16q32e128 | 10747 | 3 | 0 | 0 |
| t8h16q64e128 | 10747 | 3 | 1 | 0 |

三个配置共32241次固定向量计算。完整按精度 exact 数量、max_ulp 和代码指纹见 [JSON](mixed-cmodel-v1.7.json)。误差为与独立 Fraction 精确数学参考最后一次FP32 RNE的比较；最大3ULP来自既有BF16数据，不承诺任意严重抵消输入的普遍ULP上界。

构建：`.deps/cmake-3.28.4/bin/cmake --build src/cmodel/build -j 4`。
验证：`python3.11 -m unittest discover -s test/tests -v`，31项通过。新增5项覆盖全量数据、QE/多精度全部S1–S8断点相同、闲置端口毒化/负零、三组窗口的S5 token与S7树宽、逐拍换型/气泡/同步复位取消。既有多精度/E/数学参考测试一起通过。

输入按64位group拆分；源scale稀疏槽已由数据适配器展开，C只在总后端计一次。QE复用现有Q/E数值函数并对S2的W4/W8/U6范围做断言；混合状态按实际前端逐级推进，不用修改K_FP16扩大高精度能力。

后续：建立RTL，独立导出和Verilator验证后再以1GHz启用clock gating和时序优先DC。此记录不作为RTL/PPA通过依据。
