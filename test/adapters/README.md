# 实现适配层

为 CModel、Chisel 导出 RTL 和手写 Verilog 提供统一测试入口。只做接口连接与约定的序列化，不修正运算结果、不补拍掩盖延迟差异。离线文件或联调接口在验证合同中确定，当前无实现。

当前 [cmodel.py](cmodel.py) 负责 DP_INPUTS_V1 的纯打包读写、JSONL 调用及校验和，不包含数值运算。未来 RTL 驱动读取同一文件。
