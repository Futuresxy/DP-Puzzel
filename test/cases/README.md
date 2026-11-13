# 共用测试用例

现用实现使用相同逻辑输入和控制场景，记录随机种子及来源；新增架构先准备独立数学数据，再接入对应 CModel/RTL 验证，不预填未实现的逐位期望。

当前 [import_legacy.py](import_legacy.py) 只读转换原九格式；[generate_extensions.py](generate_extensions.py) 固定种子生成 TF32/INT8。格式字段/广播仅在导入时转换一次。

[import_petile_ratio.py](import_petile_ratio.py) 只读导入 `petile_full16_fp48` 的原生 E96、`petile_full16_fp416` 的原生 E128 和 `petile_full16_low16` 的原生 Q64。每种格式保留原五段共961笔；不截取 K、不新增随机数据、不读取 fp432。它展开源文件的稀疏 scale 槽位、转换 FP6 编码位置、保留 HiF4 元数据和单个 C，再生成独立精确数学 golden。再生命令和与现用回归的边界见 [数据合同](../data/README.md#逻辑-k-扩展数据-dp_logical_vectors_v1)。
