# 实现适配层

为 CModel、现用手写 Verilog 和未来 Chisel 导出 RTL 提供测试适配。只做接口连接与约定的序列化，不修正运算结果、不补拍掩盖延迟差异。

当前 [cmodel.py](cmodel.py) 负责 DP_INPUTS_V1 的纯打包读写、JSONL 调用及校验和，不包含数值运算；现用 RTL 驱动读取同一文件。

[logical.py](logical.py) 独立读写并校验 `dp_logical_vectors_v1`：实际逻辑K、每group的scale、FP6位置和HiF4元数据。它为待实现的混合 DP 保存逻辑测试数据，不设置虚假的K_FP16，不调用CModel或RTL；后续需按新profile接入物理端口适配。
