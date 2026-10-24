# DC 输入契约 v2

硬件链只计算 **一个 RTL 目录指纹**。配置、工具、库、回执、报告和网表不再逐文件保存 SHA-256；它们保留路径、版本、原始报告和实际状态。

## RTL 和真实验证证据

export 位于 `hw/rtl/<export-id>/`，内含 README.md、manifest.json、files.f、src。ID 末尾 12 位来自同一个 RTL 目录指纹。导出与验证属于 hw/test；DC 只读消费，不内置 testbench 或精度测试。

```json
{
  "schema_version": 2,
  "export_id": "明确导出ID",
  "top": "实际顶层名",
  "status": "generated 或 passed 或 failed",
  "rtl_fingerprint": "单个目录SHA-256",
  "module_map": {
    "实际模块名": {"chisel_class": "package.Class", "source_file": "hw/chisel_src/...scala"}
  },
  "files": [{"path": "src/实际模块.sv", "role": "source"}],
  "verification": {"path": "hw/test/runs/实际ID/verification.json"}
}
```

目录指纹按稳定相对路径顺序，将 files.f 和 src/ 全部文件的路径、长度、原始字节加入同一个 SHA-256。不包含 manifest/README 等元数据，避免循环；移动目录不改变指纹，修改、增删或重命名 RTL/头文件及改变 files.f 会改变指纹。实现为 scripts/rtl_gate.py 的 rtl_fingerprint。

files.f 每行一个相对 export 的源文件，与 files 中 source 的顺序一致；header 单独列出但不独立编译。禁止未列出的 payload、外部/宏生成 include、路径穿越或符号链接。手写 SV 使用 source_language=systemverilog、chisel_class=null、source_file/rtl_file 路径映射，检查源模板与导出内容逐字节一致，不写单文件指纹。

verification.json 的 schema_version=2，包含 export_id、verification_id、同一个 rtl_fingerprint、实际 method=systemverilog_testbench、status、numerical_pass、protocol_pass、finished_utc、仿真工具版本、命令、数值判据、覆盖和种子。inputs 只记录 path/role，至少有 testbench/reference/vectors/log。门禁要求真实通过且目录指纹一致，并检查输入存在；testbench/reference/vectors 比验证时间新时要求重测。这是修改时间的过期检查，不是逐文件密码学完整性校验。

回执只能由真实仿真成功后产生；门禁不生成或升级 PASS。配置、测试或数值语义变更仍应重新验证，不能修改状态伪造通过。

## 工艺、本机与综合策略

technology JSON 记录 process、PVT、库标识、operating condition、面积单位与可选 multi-Vt。machine.local.json 绑定实际绝对工具/DB/环境路径，默认忽略；不存密码或许可证凭据。

constraints JSON 显式给出时钟、IO min/max、transition、load、面积恢复、hold 修复等。clock_gating 默认 true，最小门控位宽默认配置为 4；可显式设为 false。布尔值必须为 JSON 布尔类型，时间/负载单位为 ns/pF。

```json
"hierarchy": {
  "keep_modules": ["PE*", "Pe*", "pe_*", "SubPE*", "ProcessingElement*"],
  "expand_modules": [],
  "expand_instances": [],
  "expand_depth": 0
}
```

默认不展开，保留全部层级；keep_modules 匹配的 PE 及其子树优先保护。展开维度为顶层以下的深度、模块 reference pattern 和完整实例 path pattern。只展开选中的边界，不递归 flatten；其余边界通过 no_autoungroup/no_boundary_optimization 保留。若确需展开默认保护的 PE，显式调整 keep_modules。常量传播和模块内部优化仍可能去掉无用逻辑。

## 运行和结果

run ID 固定 `dc_<RTL顶层名>_<MMDDHHMM>`，使用 Asia/Shanghai（UTC+08）时间；同顶层同分钟重名立即拒绝，不加随机尾缀、不覆盖。自选 --run-id 也必须满足该格式并与 top 一致。

--purpose 记录综合目的。完整约束和本机绑定在 inputs/resolved.json 快照；综合前核对配置未变、库可读和 RTL 门禁，运行后再检查 RTL。原始报告和网表按固定路径关联，不生成逐文件输入/输出指纹清单。
