# DP CModel

当前实现：C++17 整数位精确模型、逐级周期模型，支持 11 种 datatype、K4/K8/K16。默认共享八级 T8H16Q32E64，C 在 S5 解包，S8 输出 FP32 RNE 或 INT32 回绕。NVFP4/HiF4 共用 signed15×positive signed9 scale 乘法。

规格入口：[CModel 合同](../spec/dp/cmodel.md)、[DP 接口](../spec/dp/interface.md)、[逐级位宽](../spec/dp/stage-formats.md)。测试数据共用根 [test/](../../test/README.md)。当前尚无新 RTL 或 PPA 结果。

## 构建和测试

依赖 C++17 编译器、CMake≥3.16、Boost **1.83.0**、nlohmann_json **3.11.3**、Python3≥3.9。版本固定，优先使用系统包；缺失时可按依赖记录的 URL/SHA 获取固定 release 到忽略的 `.deps/`，通过 CMAKE_PREFIX_PATH/BOOST_ROOT 选择；来源与哈希见 [依赖记录](../../dependencies/cmodel.json)。

```sh
cmake -S src/cmodel -B src/cmodel/build -DCMAKE_BUILD_TYPE=Release
cmake --build src/cmodel/build -j 2
python3 test/run_cmodel.py --phase existing
python3 -m unittest discover -s test/tests -p test_existing.py -v
python3 test/run_cmodel.py --phase extensions
python3 -m unittest discover -s test/tests -v
```

已提交 packed 数据可直接测试，无需旧目录可用。重新导入已有源数据执行 `python3 test/cases/import_legacy.py`；这会重建新版数据/manifest，之后通过 `--write-goldens` 重建已验证期望。扩展数据用 `python3 test/cases/generate_extensions.py` 重建。不要手改 expected 来消除失败。

sanitizer 构建位于已忽略的 build/ 内：

```sh
cmake -S src/cmodel -B src/cmodel/build/sanitize -DCMAKE_BUILD_TYPE=Debug -DDP_SANITIZE=ON
cmake --build src/cmodel/build/sanitize -j 2
python3 test/run_cmodel.py --phase all --binary src/cmodel/build/sanitize/dp_cmodel_cli --run-dir test/runs/cmodel/sanitize
```

## API 和执行器

[model.hpp](include/dp/model.hpp) 提供 `evaluate(Config, Request, trace)` 和 `Pipeline::step(...)`。逐周期版本在每拍计算对应级，允许并行在途和逐请求换型。沿 n 接收，step(n+8) 返回输出；reset 清空，不等 last 排空。

CLI `dp_cmodel_cli [--config FILE] [--trace]` 从 stdin 读取 JSONL，逐行输出 JSONL。操作包括：

```json
{"op":"config"}
{"op":"eval","request":{"id":0,"a_datatype":1,"b_datatype":1,"c_datatype":0,"a_scale_datatype":0,"b_scale_datatype":0,"last":true,"a":"3c00","b":"3c00","c":"00000000","a_scale":"0","b_scale":"0","a_e1":"0","a_e2":"0","b_e1":"0","b_e2":"0"}}
{"op":"step","reset":true}
```

eval 示例是一个 FP16 非零乘积加零，其余元素为零，默认 K16，结果 0x3f800000。step 接收同样的 request 并带 a_valid/b_valid/c_valid；无有效输入用 `{"op":"step"}` 注入气泡/排空。输出 ready/accepted/valid，只有 valid=true 时带 result。id 只是软件验证关联，不增加硬件端口。

四项配置默认：

```json
{"k_fp16":16,"local_shift_mag_width":27,"global_signed_align_width":40,"post_scale_norm_extra_stage":0}
```

`--trace` 给出 S1–S8 的实际数值观察点及逐拍寄存状态；大整数以十进制字符串输出，输入及最终 d 以十六进制表示。不要把 trace 内软件保存的历史字段计入硬件寄存面积。

## 模块和测试结论

- `lib/unpack.cpp`：E/M/S、scale 分类和 C 解包。
- `lib/lane.cpp`：乘法重构、指数/MAX、局部 RTZ 与 lane 树。
- `lib/group.cpp`：共享 scale、LZD 计数、一次双向全局对齐、总树、输出。
- `lib/arithmetic.cpp`：显式有限窗口/自然增长断言及整数实现 RNE。
- `lib/model.cpp`：事务/周期调度；`lib/json_io.cpp`：协议检查。

[首批报告](../../test/results/cmodel-v1.4.md) 区分“匹配有限位宽架构”与“相对精确数学的误差”。CModel通过不等于RTL、1.41GHz或PPA通过。
