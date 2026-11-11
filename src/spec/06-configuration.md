> 功能：定义参数及其合法派生关系；范围：构建参数、模式容量、位宽和频率规格常量；版本：v1.5.7；修改时间：2026-11-05 17:20:00 +08:00；对应代码：[CModel include/dp/config.hpp](../cmodel/include/dp/config.hpp)；分组主方案手写 RTL：[dp_top.v](../verilog/top/dp_top.v)；Chisel 尚未实现。

# 参数与派生关系

CModel 参数入口为 [config.hpp](../cmodel/include/dp/config.hpp)，RTL 通过 [dp_top](../verilog/top/dp_top.v) 的构建参数传入。后续 Chisel 使用等价参数对象。

## 1. 可配置项

| 参数 | 默认值 | 合法性与作用 |
| --- | ---: | --- |
| `frontend`（仅 CModel） | `multi` | `multi` 或 `e`；静态前端选择，非请求 datatype |
| `k_fp16` | 16 | 4、8、16；决定 G=1/2/4；E 前端为 E16/E32/E64，不启用 FP16 |
| `local_shift_mag_width`（RTL `LOCAL_W`） | 28 | 至少 27；S3 幅值窗口，T/H/Q 的 F=width−2 |
| `global_signed_align_width`（RTL `GLOBAL_W`） | 40 | S6 含符号窗口，实际幅值移位器为 width−1 |
| `post_scale_norm_extra_stage` | 0 | 0 或 1；固定 L8 或备用 L9，不逐笔变化 |

两级窗口独立配置。合法性约束为 `GLOBAL_W >= max(LOCAL_W+4,33)`，保证组幅值和 C 都能放入 S6 幅值槽。模型允许的窗口是探索空间，不表示每个窗口都通过 35/37 位整体精度验收。软件还检查指数/索引类型可表示性，拒绝未知配置键、负数、小数和越界值。

## 2. 结构和格式常量

| 具名量 | 定义 |
| --- | --- |
| 基本组 FP16 容量 / lane 数 | 4 / 2 |
| 每 lane T/H/Q/E 元素数 | 1 / 2 / 4 / 8；INT8 同 Q |
| 每 lane 乘法器组数 | 2 |
| 高/低分片位数 | 8 / 4；形成 HH、HL、LH、LL |
| HiF4 e1/e2 位数 | 各 1；分别覆盖 4/8 个元素 |
| E 幅值 / scale 幅值 | 各 4 位；scale 幅值小数位 3 |
| 固定解包 E/M/S | 10 / 16 / 4 位 |
| FP32 / INT32 容器 | 32 位 |
| 目标频率 | 1_410_000_000 Hz；周期由频率派生 |

固定格式不意味着所有常量都可任意改变。构建参数、规格常量和派生量必须区分，不能为中间每条连线增加互相矛盾的自由旋钮。

## 3. 容量与自然增长

以下 leaf/lane/group 为多精度主路径宽度；公共 S5 的 M_group、S6/S7 和容量推导也适用于 E 前端。E64 实际配置见 [e64.json](../configs/dp/e64.json)。

```text
L(n) = ceil(log2(n)), L(1) = 0
G = k_fp16 / 4
lanes = 2 * G
K_mode = lanes * elements_per_lane(mode)
packed_AB_bits = 16 * k_fp16
W_leaf = local_shift_mag_width + 1
W_lane = W_leaf + L(4)
W_group = W_lane + L(2)
M_group = W_group - 1
M_global = global_signed_align_width - 1
N_top = G + 1
W_sum = global_signed_align_width + L(N_top)
F_local_THQ = local_shift_mag_width - 2
F_global_float = global_signed_align_width - 2
pad_group_to_global = M_global - M_group
pad_C_to_global = M_global - 32
latency = 8 + post_scale_norm_extra_stage
```

K4/K8/K16 对应 G=1/2/4，含 C 的总树为 2/3/5 项，深度 1/2/3，默认输出宽 41/42/43。非二次幂树逐层配对，未配对叶直传，不丢增长位。

## 4. E 与 scale 的共享宽度

```text
E_guard = 2 * (2^hif_e2_bits - 1)
W_E_pair = 2*E_magnitude_bits + 1 + L(2)
W_sop_scale = W_E_pair + E_guard + L(E_pairs_per_lane) + L(lanes_per_group)
W_sop_magnitude = W_sop_scale - 1
W_factor = 2 * scale_magnitude_bits
W_product_magnitude = W_sop_magnitude + W_factor
pad_scale_product = M_group - W_product_magnitude
```

由此得到 guard=2、pair W10、紧凑 SOP W15、幅值 W14、系数 W8 及无符号积 W22。E 前端内部 S2 pair/S3 lane/S4 group 为 W10/W12/W15，LOCAL_W 仅决定公共输出 M_group=LOCAL_W+3 和补零；内部不增加移位精度损失。默认低补 9 位进入 M31。幅值上界与 F 见 [scale](dp/group/scale.md)。

## 5. 指数与控制宽度

8 位元素指数相加须保留 9 位，5 位指数相加须保留 6 位，scale 指数和须保留 9 位。anchor 范围按 bias、F 与容器位权推导。RTL 按全局幅值上限推导共享有符号指数宽度，以覆盖源 LZD 计数及输出指数运算。先用完整差值判断方向/饱和，再编码移位控制，不能截高位回绕。

默认各级范围见[出口表](dp/common/stage-formats.md)。datatype 编码来自[接口](dp/dptop/interface.md)，不随配置禁用某模式而重排。模块参数固定，运行时控制逐请求传递。

## 6. 阵列与未来扩展

当前 DP-Group 为 4×4，竖直组数 4，因此 TensorCore 为 16×4、共 64 个 DP；这些阵列结构尚未实现。专用 Q/QE、混合组及额外 1–2 级需另定 profile，不能与 L9 备用自动叠加。
