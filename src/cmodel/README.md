# DP CModel

当前默认 `frontend=multi` 对应 [dp_top v1.8](../spec/dp/dptop/dp-top-v1.8.md)。`legacy_multi=true` 仅用于旧多精度前端回放；混合顶层自动保留旧前端语义。E/QE/混合版本尚未迁移。数学 golden 不变，有限窗口策略参考单独位于 `test/reference/architecture.py`。

当前实现：同一个 C++17 整数位精确/逐级周期模型提供两种静态前端。默认 `multi` 支持 11 种 datatype、T8H16Q32E64；`e` 支持 MXFP4/NVFP4/HiF4、E64。两者在 S5 交付同宽 group token，共用 C 解包/LZD 和 S6–S8 后端，默认 L8/II=1。NVFP4/HiF4 使用 14×8 无符号 scale 乘法，符号独立传递。

规格入口：[CModel 合同](../spec/dp/implementation/cmodel.md)、[DP 接口](../spec/dp/dptop/interface.md)、[逐级位宽](../spec/dp/common/stage-formats.md)。测试数据共用根 [test/](../../test/README.md)。综合结果见 [DC 记录](../../hw/dc_syn/records/README.md)。

## 构建和测试

依赖 C++17 编译器、CMake≥3.16、Boost **1.83.0**、nlohmann_json **3.11.3**、Python3≥3.9。版本固定，优先使用系统包；缺失时可按依赖记录的 URL/SHA 获取固定 release 到忽略的 `.deps/`，通过 CMAKE_PREFIX_PATH/BOOST_ROOT 选择；来源与哈希见 [依赖记录](../../dependencies/cmodel.json)。

```sh
cmake -S src/cmodel -B src/cmodel/build -DCMAKE_BUILD_TYPE=Release
cmake --build src/cmodel/build -j 2
python3 test/run_cmodel.py --phase existing
python3 -m unittest discover -s test/tests -p test_existing.py -v
python3 test/run_cmodel.py --phase extensions
python3 -m unittest discover -s test/tests -v
python3 test/run_cmodel.py --frontend e --phase all
```

已提交 packed 数据可直接测试，无需旧目录可用。重新导入已有源数据执行 `python3 test/cases/import_legacy.py --source-root /path/to/legacy-corpus`；这会重建新版数据/manifest，之后通过 `--write-goldens` 重建已验证期望。扩展数据用 `python3 test/cases/generate_extensions.py` 重建。不要手改 expected 来消除失败。

E 回归复用三种精度各 961 笔输入，同时比较已有多精度结果和独立精确数学参考；不覆盖或重写原有 golden。`test_e_frontend.py` 另检查各级数值、HiF4 坐标转换、特殊值和周期。这些运行仅验证 CModel；E 专用 RTL 另由 [E64 Verilator 回归](../../test/results/e64-v1.5.8.md) 验证。

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

默认配置（省略 `frontend` 时兼容原来的多精度入口）：

```json
{"frontend":"multi","k_fp16":16,"local_shift_mag_width":28,"global_signed_align_width":40,"post_scale_norm_extra_stage":0}
```

E64 配置为 [e64.json](../configs/dp/e64.json)。原始 CLI 可执行 `src/cmodel/build/dp_cmodel_cli --config src/configs/dp/e64.json --trace < requests.jsonl`，请求 JSONL 的字段和编码不变。`frontend` 在构造模型时选择，`datatype` 仍可逐笔换型；E 前端拒绝其他格式及 INT32 C。兼容参数 `k_fp16=4/8/16` 在 E 配置中只表示 G=1/2/4，即 E16/E32/E64，并不启用 FP16。LOCAL_W 控制 E 的兼容输出容器及补零，内部 pair/lane/group 位宽固定为 10/12/15；GLOBAL_W 继续控制公共后端。混合配置见下节。

`--trace` 给出 S1–S8 的实际数值观察点及逐拍寄存状态；大整数以十进制字符串输出，输入及最终 d 以十六进制表示。不要把 trace 内软件保存的历史字段计入硬件寄存面积。

## 模块和测试结论

- `lib/unpack.cpp`：E/M/S、scale 分类和 C 解包。
- `lib/lane.cpp`：乘法重构、指数/MAX、局部 RTZ 与 lane 树。
- `lib/group.cpp`：多精度 S5 组和、幅值分离与 scale。
- `lib/lane/lane_e.cpp`：E 的 S2 乘法/pair、S3 四项树。
- `lib/group/group_e.cpp`：E 的 S4 lane 小左移/组和/abs、S5 scale 与兼容 token。
- `lib/top/backend.cpp`：共用的 S5 C 解包/LZD、S6 一次双向全局对齐、S7 总树、S8 输出。
- `lib/arithmetic.cpp`：显式有限窗口/自然增长断言及整数实现 RNE。
- `lib/model.cpp`：事务/周期调度；`lib/json_io.cpp`：协议检查。

[首批报告](../../test/results/cmodel-v1.4.md) 区分“匹配有限位宽架构”与“相对精确数学的误差”。CModel通过不等于RTL、1.41GHz或PPA通过。

命名：内部数值变量区分 exponent_field/fraction_field/fractional_bits，状态采用 config/state/token 等职责名；C++ 每项声明独立，使用两空格缩进、100 列目标。JSON 字段兼容原协议，reset=true 表示软件复位事件，对应现用 RTL rst_n=0。

## v1.7 混合组

新增 frontend `qe`（仅 Q/E，同原 Q/E 数值流水），以及 `t8h16q32e96`、`t8h16q32e128`、`t8h16q64e128`。三种混合配置位于 `src/configs/dp/` 同名 JSON；基础 k_fp16 固定16、L8，物理组数6/8，实际各格式容量由能力矩阵决定。窗口继续可调。

`lib/top/mixed.cpp` 每物理组保存自己的 S1–S5 状态；基础组调用 multi，扩展调用 E 或 QE。关闭组不解包其 payload，也不参与数值 MAX、特殊值和负零归约。`lib/top/backend.cpp` 在同一公共指数下逐源对齐，基础四组+C与扩展组分别求和再合并；高精度旁路扩展。

运行 `python3.11 -m unittest discover -s test/tests -p test_mixed_frontend.py -v`，精度摘要写入 `test/runs/cmodel/mixed_summary.json`；固定数据与精确 golden 不覆盖。新架构接受上半区闲置端口的任意位模式，只校验当前参与组。Q/MX/HiF scale 广播仍按32/32/64元素块检查，含E96尾部部分块。
