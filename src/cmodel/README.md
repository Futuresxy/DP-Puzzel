# CModel

状态：等 DP 数值细节与输入协议闭合后即可启动。本轮已确定当前主方案、T2H4Q8E16 容量层次、scale/metadata 分组、DP 内 FP32 C 与八级周期目标；尚无 CModel 实现。

CModel 需要同时提供两种可核对视图：**事务级**的有限位宽数值计算，及**周期级**的 valid、原子 A/B/C/scale/metadata 接收、固定延迟输出、last 和 mode 会话状态。周期级输出必须能与同一周期定义的 RTL testbench 对齐；关键中间 cutpoint 可记录 lane token、组 token、跨组和及 C 合并结果，便于定位差异。

浮点主路径按 8 周期建模；INT8 按最终确认的短旁路延迟建模。CModel 明确每个阶段的符号表示、定点小数点/指数坐标、位宽、自然增长与舍入。FP32 数学参考单独用于误差评价，不替代有限位宽的硬件行为模型。

实现语言、构建系统/API 和 golden 序列化格式待 CModel 规格冻结时决定。测试入口共用根目录 [test/](../../test/README.md)，不在此复制另一套验收规则。
