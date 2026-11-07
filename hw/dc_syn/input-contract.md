# DC 输入契约 v2

硬件链只计算 **一个 RTL 目录指纹**。配置、工具、库、回执、报告和网表不再逐文件保存 SHA-256；它们保留路径、版本、原始报告和实际状态。

## RTL 和真实验证证据

export 位于 `hw/rtl/<export-id>/`，内含 README.md、manifest.json、files.f、src。由 `test/` 生产验证回执，DC 只读消费快照与证据。下面为通用 schema v2，DP schema v1 见后文。

```json
{
  "schema_version": 2,
  "export_id": "明确导出ID",
  "top": "实际顶层名",
  "status": "generated 或 passed 或 failed",
  "rtl_fingerprint": "单个目录SHA-256",
  "module_map": {
    "实际模块名": {"chisel_class": "package.Class", "source_file": "src/chisel/...scala"}
  },
  "files": [{"path": "src/实际模块.sv", "role": "source"}],
  "verification": {"path": "test/runs/实际ID/verification.json"}
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

## 新版 DP 快照兼容入口

`DP_verilog_<16 hex>` 使用 RTL 分支已有 schema v1，`scripts/dp_rtl_gate.py`
核对源入口、导出清单、源指纹、RTL_ID 注释后的逐字节内容及单个
`files.f + src/` 目录指纹。保留 v1 的历史 SHA 字段以兼容原始快照 ID；不新增库/报告/网表散列清单。

真实回归生产器 `test/adapters/rtl.py` 在完整 Verilator lint、11 格式与六组参数
全部通过后产生 `test/runs/verilog/<UTC>/verification.json`。
回执显式包含命令、版本、时间、种子、参数、L8/II1、逐组仿真日志、结果和输入路径；
测试源码、CModel 源码/二进制和输入数据在运行开始后变化即要求重测。
每次回归开始撤销旧 eligibility；失败/部分回归不能启用后端。
门禁独立复核 10747 默认数值输出、2922 混格式输出、231654 断点、日志及数据，
不能通过直接修改 `ppa_eligible` 绕过。

DP manifest 记录 `top=dp_top` 和 `interface`，其中 `clock_port=clock`，`reset_port=rst_n`，复位同步低有效。DC 检查时钟配置与接口一致，复位作为同步输入正常计时。

当前后端准入参数为 `K_FP16=16, LOCAL_W=28, GLOBAL_W=40`。历史综合记录的局部窗口为 27。
其余参数虽有功能覆盖，必须另行建立对应综合配置合同。DC 显式使用
`analyze -format verilog` 与 `elaborate -parameters`，只消费主实现 19 个 `.v` 与两份头文件。

E-only 使用 `DP_verilog_e_<16 hex>`、top=dp_top_e 和 src/verilog/files_e.f（15 个 `.v`，共用两份头文件）。接口、K16/28/40、L8/II1 和目录指纹规则相同，frontend=e 单独记录。E 完整门禁要求三格式各 961 笔、5288 笔定向输出、六组参数各 137 笔有效输出与 7 笔复位取消、1106924 个 S1–S7 断点。未知前端、top/清单混用、部分回归及源漂移均拒绝；不继承 multi 的验证回执。

混合 profile 使用 `DP_verilog_t8h16q32e96_<hash>`、`DP_verilog_t8h16q32e128_<hash>`、`DP_verilog_t8h16q64e128_<hash>` 和独立 filelist/top。真实验证入口为 `test/run_mixed_verilog.py --frontend <profile>`：11种精度的10747笔全量输出、三组窗口的混格式/定向/复位检查及S5–S7断点，全部通过才生成后端回执。基础/E64旧门禁要求保持不变。

`prepare --timing-repair-from <run>` 只接受同一已验证RTL、工艺、最终约束及机器绑定的完整有效映射DDC，不接受失败工具/缺报告/忽略设置的run。修复使用临时增加50ps的setup uncertainty做最多两次增量优化，再恢复原始setup预算；hold修复临时增加1ps后同样恢复。源run、两种guardband与最终结果分别记录，不改变用户要求的最终1ns周期、IO延迟或uncertainty，不引入false/multicycle path或retiming。

`design_rule_repair` 可引用原始有效映射或其一次 setup/hold 修复；完整核对父链、冻结 RTL 和约束。它执行电气设计规则修复后重新检查 hold，最终不放宽时钟/IO/uncertainty。报告的 flow_pass 还要求 max_capacitance/max_transition/max_fanout 无违规；setup/hold 状态单独保留，便于识别时序通过但电气规则失败。
