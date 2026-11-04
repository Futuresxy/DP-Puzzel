# 共用测试用例

等待新 spec 定义数据格式、模式、边界和协议后建立用例。三种实现使用相同逻辑输入和控制场景，记录随机种子及来源；不预填旧版数据或精度阈值。

当前 [import_legacy.py](import_legacy.py) 只读转换原九格式；[generate_extensions.py](generate_extensions.py) 固定种子生成 TF32/INT8。格式字段/广播仅在导入时转换一次。
