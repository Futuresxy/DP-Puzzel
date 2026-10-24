# DC / 统一 RTL 门禁 v1

由 `scripts/rtl_gate.py` 与 DC 驱动执行。已有 scripts/dc_example.py 为 BF16 最小手写例子生产 export 和真实 SV 回执；完整 Chisel exporter/通用验证入口仍待实施。只有真实 testbench 成功后才能写 passed，不能人工填写。hash 为文件原始字节 SHA-256。

## RTLExport

目录名为 `<Top>__<config-id>__<YYYYMMDDTHHMMSSffffffZ>__<source-sha12>`，位于 hw/rtl。必须有 README.md、manifest.json、files.f 和 src。以下仅说明字段，不是可用的通过证据：

```json
{
  "schema_version": 1,
  "export_id": "完整导出目录名",
  "top": "实际顶层名",
  "status": "generated 或 passed 或 failed",
  "module_map": {
    "实际模块名": {"chisel_class": "package.Class", "source_file": "hw/chisel_src/...scala"}
  },
  "files": [
    {"path": "src/实际模块.sv", "sha256": "实际摘要", "role": "source"},
    {"path": "src/实际头文件.svh", "sha256": "实际摘要", "role": "header"}
  ],
  "verification": {"path": "hw/test/runs/实际ID/verification.json", "sha256": "实际回执摘要"}
}
```

files.f 每行一个相对 export 的 source 路径，与 files 中 source 顺序完全一致。不接受 glob、绝对路径、编译选项、重复源或嵌套清单。header 不独立编译，但纳入 manifest 和验证 hash。src 内所有文件必须列入 manifest；include 必须是 export 内唯一可解析的字面量路径，不支持外部/宏生成 include。

exporter 仍需保证完整模块映射；门禁检查 top 映射和来源字段，不解析 Verilog 语义。源码、硬件参数、生成工具版本与 source-sha 生成规则由未来 exporter 补充，本次不声称实现了完整导出链。

用户授权的手写 RTL 示例可使用显式映射扩展：source_language=systemverilog、chisel_class=null、source_file 为仓库内源模板、source_sha256 为模板摘要、rtl_file 为对应 source 清单路径。门禁要求模板 hash 未变且等于导出 RTL hash，即逐字节导出；不填虚构 Chisel 类。不指定 source_language 的旧映射仍按 Chisel 验证。示例入口为 scripts/dc_example.py，不是通用 Chisel exporter。

## RTLVerification

回执必须在 hw/test/runs，schema_version=1，相对路径以仓库根为基准：

| 字段 | 要求 |
| --- | --- |
| verification_id / export_id | 明确 ID，与 manifest 一致 |
| status / method | passed / systemverilog_testbench |
| numerical_pass / protocol_pass | 均为布尔 true |
| rtl_sha256 | src/... → hash 字典，与 manifest 全部 source/header 一致 |
| files_f_sha256 | 被验证的 files.f 摘要 |
| command / simulator.version | 实际命令和仿真器版本 |
| numeric_semantics | 实际语义版本及数值判据 |
| coverage_matrix / seeds | 实际覆盖矩阵和随机种子列表，不得空缺 |
| inputs | path、sha256、role 列表，至少包含 testbench/reference/vectors/log 四类 |

所有输入/日志保留可核验文件；验证代码、参考或向量变化后旧回执失效，必须重跑。门禁核验现有证据一致性，不为任意人工 JSON 提供真实性认证；受控证据生产器及审查仍必需。没有真实回执时 check/prepare/run 全部停止。

## 综合配置

technology 固定库 ID、process/PVT、operating library/condition、wire_load_model、area_unit 与 multi_vt。DB 路径只在本机文件映射，逐个 hash；reference_dc_version 是来源版本，实际版本另记录，不表示其他版本已验证。

constraints 全字段显式填写，未知字段拒绝，避免拼写错误静默回退。period > 0，IO min 可负且不超过 max，其余时间/负载非负，策略为 JSON 布尔类型。全部版本变化形成新 run。

machine 只含 schema_version、dc_shell、setup_script、libraries；工具为可执行绝对路径，setup 可为空，库为 ID → 可读 DB 绝对路径，basename 必须匹配库 ID。许可证由批准的外部环境入口提供。启动禁用 home/local DC setup；安装目录管理员 setup 仍由该 EDA 安装与版本管理。
