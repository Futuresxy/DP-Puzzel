# 四组 E64 / Q32E64 验证 v1.7.4

CModel/spec 检查点 `2db339d`。固定四组、LOCAL28/GLOBAL40、L8/II=1。E group 不修改，QE 使用既有 COMPACT_UNPACK=1；顶层只装配五源浮点后端。

CModel 三项检查通过：固定容量、支持格式/非法拒绝、E/QE 别名逐级等价和五源总和；QE 同时与 multi 比较逐级数值。40项 DC/RTL 门禁软件测试通过，不能代替 RTL/DC 测量。

| 顶层 | 格式 | CModel 一致 | 数学一致 | 最大 ULP |
| --- | --- | ---: | ---: | ---: |
| e64 | mxfp4_e2m1 | 961/961 | 961/961 | 0 |
| e64 | nvfp4 | 961/961 | 961/961 | 0 |
| e64 | hif4 | 961/961 | 961/961 | 0 |
| q32e64 | mxfp8_e4m3 | 961/961 | 961/961 | 0 |
| q32e64 | mxfp8_e5m2 | 961/961 | 958/961 | 1 |
| q32e64 | mxfp6_e3m2 | 961/961 | 961/961 | 0 |
| q32e64 | mxfp6_e2m3 | 961/961 | 961/961 | 0 |
| q32e64 | mxfp4_e2m1 | 961/961 | 961/961 | 0 |
| q32e64 | nvfp4 | 961/961 | 961/961 | 0 |
| q32e64 | hif4 | 961/961 | 961/961 | 0 |

完整逐格式测试没有复位取消。随机/定向压力流另外插入缺少 A/B/C、气泡、流水中复位、非法类型、模式切换；取消仅指复位清除在途请求。每个窗口重放所有 E nibble/scale/HiF 元数据定向请求及随机组输入。S5四个组+C、S6五个叶子/common anchor、S7完整总和逐项核对。

| 顶层 | 窗口 | 事务计数 | 断点 |
| --- | --- | --- | ---: |
| e64 | 27/40 | PASS cycles=6610 accepted=5458 checked=5025 cancelled=433 | 57253 |
| e64 | 28/40 | PASS cycles=6610 accepted=5458 checked=5025 cancelled=433 | 57253 |
| e64 | 32/64 | PASS cycles=6610 accepted=5458 checked=5025 cancelled=433 | 57253 |
| q32e64 | 27/40 | PASS cycles=6829 accepted=5642 checked=5195 cancelled=447 | 59197 |
| q32e64 | 28/40 | PASS cycles=6829 accepted=5642 checked=5195 cancelled=447 | 59197 |
| q32e64 | 32/64 | PASS cycles=6829 accepted=5642 checked=5195 cancelled=447 | 59197 |

Verilator 5.030，纯Verilog2005；每配置顶层 lint 无 warning/error。数学 golden 来自 test/data/dp 的 exact_fp32_or_int32，硬件一致性依据对应 E/QE CModel，不能用数学低ULP代替 bit-exact。

| 顶层 | 验证 run | export |
| --- | --- | --- |
| e64 | `20261108T004627771406Z` | `DP_verilog_e64_628e283760c4e830` |
| q32e64 | `20261108T004633001215Z` | `DP_verilog_q32e64_7600e600b2574f57` |

复现：

```bash
source /opt/rh/gcc-toolset-10/enable
export CCACHE_DISABLE=1
export CXXFLAGS='-std=c++20 -fcoroutines'
export VERILATOR=/eda/verilator/v5.030/bin/verilator
python3.11 test/run_lowp_verilog.py --frontend e64
python3.11 test/run_lowp_verilog.py --frontend q32e64
```

PPA 由独立 DC 报告记录，本文件只证明相应快照的功能/协议。原始数据和波形/构建在本地 run，JSON保存带指纹的精简回执。


RTL 自检范围为新增 dp_top_lowp/e64/q32e64；既有 group 保持原实现。逐项结果：常量含义明确、宏在vh、assign/generate组合逻辑、按位条件、无动态多维索引、DFF保存流水、单变量声明、复位类型、rN命名、payload使能、目录职责、无纯别名参数、语义变量名、无裸pack接口、特殊字段宏，共15项通过。参数合法性检查位于 synthesis translate_off，不属于功能组合逻辑。

DC 综合及同工况面积对比见 [N12/1GHz 报告](../../hw/dc_syn/records/README.md#历史记录)，独立于本文件的数值/周期证据。

六个已完成编译目录的临时C++/目标文件/仿真二进制已清理，保留lint/compile日志、输入、输出、断点与回执；清理后两快照门禁重新核验通过。复现命令会重新编译。
