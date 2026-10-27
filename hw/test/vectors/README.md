# 精确 golden 随机测试语料

`generate_random_vectors.py` 先生成原始 A/B、scale、HiF4 group bits 和 FP32 C
编码，再由独立的 `exact_dot.py` 反量化、计算精确点积及 C，最后一次 RNE 到 FP32。
参考计算只使用 Python 任意精度整数与二进制指数，不使用 FP64、DUT 对齐窗口或 RTL
截断模型。普通回归只读输入与 golden。

## 生成与运行

从仓库根目录执行：

```sh
python hw/test/vectors/generate_random_vectors.py
```

默认 seed 为 `24301`（`0x5eed`），生成到
`hw/test/vectors/generated/random_1600_seed24301/`。默认九种格式与33种格式/K
组合共52800笔独立输入。每个格式/K的随机流由用户 seed、格式名称和 K
稳定派生，选择格式或改变遍历顺序不会改变同一个 case。

自选格式、K、seed 和新输出位置：

```sh
python hw/test/vectors/generate_random_vectors.py \
  --formats mxfp4_e2m1 nvfp4 hif4 --k 64 96 128 \
  --seed 24302 --output-root hw/test/vectors/generated/random_seed24302
```

已有输出目录拒绝覆盖。生成先在同一父目录暂存，全部成功后发布，避免半份语料作为
正常结果。`generated/` 是忽略的本地产物；生成器、测试和小型结果摘要进入版本管理。
既有 `hqe-initial` 和 `initial-h-global` JSONL 向量保持原用途。

现有固定六 TB 可直接读取新 TXT：

```sh
python scripts/run_pe_tests.py \
  --data-root hw/test/vectors/generated/random_1600_seed24301 \
  --datasets random_1600
```

可追加 `--profiles k_1_2_4 --formats fp16` 缩小范围，或使用
`--schedule both` 比较连续输入与气泡调度。生成器可配置的 K 不会改变 DUT 的
native K；仿真入口仅选取该 PE/格式支持的 K。

## 每个格式/K的1600笔

| 段 | 事务编号，0-based | 数量 | 数值验收 |
| --- | --- | ---: | --- |
| `ab_scale_random` | 0–1023 | 1024 | 有限结果距 golden FP32 ≤2个可表示数间隔 |
| `special_directed` | 1024–1087 | 64 | 全部 bit-exact，含零符号与 canonical NaN |
| `c_stratified_random` | 1088–1599 | 512 | 有限结果距 golden FP32 ≤2个可表示数间隔 |

1024笔分为八类，每类128笔：normal×normal 局部指数、normal×normal 全指数、
normal×subnormal、subnormal×normal、subnormal×subnormal、逐元素混合、
normal×normal scale 边界、逐元素混合且 scale 跨度较大。

有限编码内直接随机选择符号、指数、尾数和独立 A/B 块 scale。局部指数与常用 scale
样本保证普通有限计算占主体；全指数、极端 scale 和跨度样本保留输出溢出/下溢，
不根据 DUT 结果或抵消程度筛选。BF16 的极小乘积可能最终下溢为零，case.json
逐段记录输出分类，不能把这类样本等同于有效非零结果的精度覆盖。

512笔 C 测试分为八类，每类64笔：C=0、与点积同量级同号、同量级异号、精确抵消、
近抵消、明显主导、明显较小、FP32 subnormal C。普通 C 样本使用中等指数的随机
normal A/B，并关联符号使点积非零，便于明确 C 相对点积的量级。精确抵消用成对
产品抵消后保留一个产品，保证其相反数可表示为 FP32 C；近抵消把这个 C 改为相邻
FP32 值。该构造不假设任意精确点积都能直接存入 FP32 C。

64笔由16种定向语义各配四个注入位置组成，包含 A/B 零、负零、抵消、C quiet/signaling
NaN、C ±Inf，以及该格式实际支持的元素/scale 特殊值与边界。位置包括首端、中间、
末端和块边界；小 K 下允许位置重合。无 Inf/NaN 元素编码的格式通过合法 scale NaN
及 C 测试特殊语义，不制造不存在的编码。

## 格式与 K

| 格式 | 默认 K | scale/group 合同 | 自定义 K 约束 |
| --- | --- | --- | --- |
| FP16、BF16 | 16 | 无外部块 scale | 正整数 |
| MXFP8 E4M3/E5M2 | 32/64/96/128 | 每32元素一个 E8M0 | 32的倍数 |
| MXFP6 E3M2/E2M3 | 32/64/96/128 | 每32元素一个 E8M0 | 32的倍数 |
| MXFP4 E2M1 | 64/96/128/192/256 | 每32元素一个 E8M0 | 32的倍数 |
| NVFP4 | 64/96/128/192/256 | 每16元素一个无符号 E4M3；外部 tensor scale=1 | 16的倍数 |
| HiF4 | 64/96/128/192/256 | 每64元素 E6M2；每4/8元素 group0/group1 | 8的倍数 |

MX 编码依照 [OCP MX v1.0](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)。
E8M0 `00` 是2^-127、`ff`是NaN，没有零/Inf scale。E4M3顶指数中的
`78..7e`是有限数，只有`7f`是NaN；E5M2支持Inf/NaN；FP6和E2M1没有特殊元素编码。

HiF4 固定为 [HiFloat4 原论文 v2，II-A](https://arxiv.org/html/2602.11287v2#S2.SS1)：
元素为 S1P2，即符号乘以低三位整数/4；E6M2 主 scale 为
`(4+mantissa)*2^(exponent-50)`，bias=48。
`00`为2^-48，`fe`为1.5×2^15，`ff`为NaN；无零、Inf或subnormal主scale。
逐元素还乘以`2^(group0[i/4]+group1[i/8])`。HiF4 分层采样用 S1P2
低幅值1..3/4与高幅值4..7/4，不把 E6M2 当作普通IEEE次正规格式。
K96等尾部不足64元素的块仍具有独立主scale；逻辑lane索引决定共享关系。

## 文件及精确参考语义

```text
<output-root>/
├── index.json
└── <format>/K<k>/random_1600/
    ├── inputs.txt
    ├── golden.txt
    └── case.json
```

TXT 完全沿用 [petile_ratio 数据合同](../data/README.md)：`PE_VECTORS_V2`、
13个十进制头字段，然后每事务一行原始HEX。A/B元素是16位文本容器中的原始编码，
不是转换后的FP16。TB负责物理packing及scale槽映射。`golden.txt`每行一个FP32 HEX，
全程1600笔在一个batch中处理。

case.json 的模型标识为 `integer_dyadic_dot_plus_c_rne_fp32_v1`，保存三段边界、
每笔场景、逐段分类/scale编码覆盖，以及精确参考的`coefficient/exponent/special`。
有限值代表`coefficient * 2^exponent`，系数保存为十进制字符串。输入校验器从TXT
重新精确计算，并同时核对这些记录及FP32 golden。

NaN优先传播；0×Inf与相反符号Inf相加产生NaN；NaN输出固定为`7fc00000`。
Inf保持符号。与DP公共合同一致，精确全零/抵消结果为+0；负的非零精确值下溢时保留-0。
只有最后一次FP32转换会发生规定的舍入、上溢或下溢。

普通数值采用有序FP32编码距离，正负零共享一个数值位置；距离≤2包含端点2。
NaN/Inf始终严格核对编码，64条定向测试也严格核对零符号。这个整数距离并不是
`abs(RTL-exact)/ulp32(exact)`形式的实数ULP误差。bit-exact比例仅作统计，
不设置90%门槛。旧 `correct_961` 的历史比较策略保持其原语义。

## 验证与首轮结果

```sh
python -B -m unittest discover -s hw/test/tests -p test_exact_vectors.py -v
```

测试包括独立Fraction/FP32邻值搜索对RNE的交叉核验、完整FP16有限编码、FP4/6/8码本、
HiF4分组、NaN/Inf传播、舍入边界、数据篡改拒绝与≤2门槛的包含性。

seed24301的首轮连续输入结果见
[摘要](../regressions/exact-random-1600-summary.json) 与
[分类分析](../regressions/exact-random-1600-analysis.json)：
46个PE/格式组合共73600个DUT输出，22个组合通过、24个组合数值未通过；
全部周期协议检查通过，全部2944个定向测试输出bit-exact。
失败集中于C抵消/近抵消与部分跨指数/scale样本，未调整语料或门槛来规避失败。
失败的68个独立输入用Fraction反量化/点积与独立FP32邻值搜索交叉检查，golden无差异。
这些结果尚未定位全部RTL误差根因，不构成所有参数/格式的完整验收，也不启用PPA。

## K124失败样本的逐级定位

只读诊断入口：`python -B scripts/diagnose_pe_precision.py --output hw/test/runs/k124-diagnosis-new`。
输出目录必须不存在。脚本读取显式source run及其中的RTL_ID，用同一个固定TB重放，
额外的SV层次监视器只记录SubPE、PG、PE、C及末端对齐/舍入边界，不修改设计RTL。

[定位摘要](../regressions/k124-precision-diagnosis.json)覆盖K124的54笔数值失败与对照，
共148笔重放。FP16/BF16的42笔及MXFP8 E4M3的2笔首先在PG局部对齐丢位；
MXFP8的另6笔首先在SubPE双lane对齐丢位，后续PG也可能继续引入主要误差；
MXFP4的4笔在PE跨PG对齐丢失小项。全部被观察的RTZ操作与末端RNE均符合当前算术公式，
这不意味着满足精确点积参考的≤2编码距离要求。

对45笔输入去掉精确相互抵消项、保持精确点积和C不变后，全部恢复bit-exact。
逐级数值、移位坐标、原始输入、golden及对照记录保存在摘要指向的diagnostic run中。
这些是对当前失败输入的根因证据；未修改RTL或放宽验收阈值。
