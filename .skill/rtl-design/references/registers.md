# 同步低有效复位与流水 DFF

## 模块合同

以下是后续实现约定，当前尚未建立这些 RTL 模块；建议放 `src/verilog/common/`，两个前端共用唯一实现。

| 模块 | 参数 | 端口 | 上升沿行为 |
| --- | --- | --- | --- |
| `dp_dff_sync_reset` | `WIDTH`、`RESET_VALUE` | `clock, rst_n, in_en, in_d, out_q` | `!rst_n` 复位；否则使能更新，否则保持 |
| `dp_dff_en` | `WIDTH` | `clock, in_en, in_d, out_q` | 使能更新，否则保持；无复位 |

`WIDTH >= 1`，`RESET_VALUE` 声明为 `[WIDTH-1:0]`。两个模块均为单个时钟边沿的存储，无附加流水或隐含 clock gating。`out_q` 在原语内为 reg，功能层连接 wire；signed 数据经过位向量端口后，消费者显式声明/转换为 signed。

控制原语时序核心：

```verilog
always @(posedge clock) begin
  if (!rst_n) begin
    out_q <= RESET_VALUE;
  end else if (in_en) begin
    out_q <= in_d;
  end
end
```

数据原语时序核心：

```verilog
always @(posedge clock) begin
  if (in_en) begin
    out_q <= in_d;
  end
end
```

调用层明确使能语义。对当前无背压 DP：

- valid 控制 DFF 的 `in_en=1'b1`，数据输入为上一级 valid（S1 为合法接收事件）。气泡必须推进为 0；不能用 valid 自己作为更新使能而留住旧请求。
- payload 数据 DFF 的 `in_en=rst_n && valid_previous`；复位或无效期间保持。不复位 payload，不消费无效 payload 的未定义值。
- type/last/special/sign/anchor 随所属有效数据推进。需要确定复位值的控制用控制原语，其他元数据可由有效位屏蔽；迁移不能顺便改变既有复位可观察行为。
- 一个宽实例可打包同阶段、同使能的字段，连接顺序和字段切片必须清晰；不同使能/复位语义分开。

模块化替换原有寄存器，不能在原寄存器后再增加一层。lane/group/top 的流水归属、L8 和 II=1 保持。

同步复位需要 `rst_n=0` 覆盖有效时钟上升沿，并满足采样约束；时钟停止时不会立即清零。不加入异步敏感列表，不随意插入复位同步器；外部异步复位或多时钟域需单独定义 CDC/RDC 合同。

## 综合边界

原语使用行为级 RTL，由 DC 映射标准单元；不在通用源码中绑定私有工艺 DFF。不自动添加 `dont_touch` 或强制禁止工具优化，RTL 可审查层级不等于后端必须保留 wrapper。封装本身不证明面积/功耗/时序改善。

存储宏、CDC 同步器、时钟门控具有特殊映射约束，不强行替换为普通流水 DFF；在其专用合同中定义。本次 DP 规范不引入这些新功能。

## 迁移验收

本次只建立规范，实施时作为完整接口迁移：

1. 主/E 顶层、子模块、TB 和驱动共同改名并反转复位电平，不能仅替换文本。CModel 的“复位事件”语义保持，在 RTL 驱动处映射极性。
2. 同步 spec、README、源清单、导出 manifest、RTL 门禁以及 DC/功耗入口的复位识别与约束。不改历史快照和回执。
3. DFF 层级变化后检查断点 TB、层级引用、DC 阶段识别和功耗注释路径，不能通过跳过断点来消除错误。
4. 验证复位优先于使能、气泡推进、有效保持、连续请求、在途取消、恢复首笔和非法请求。无复位数据首次写入前允许未知，必须由有效位屏蔽。
5. 多精度与 E 分别重新导出并完整回归，核对 L8、II=1、参数配置、断点、输出与取消计数。新快照的 PPA 需重新测量，不沿用历史结果。
