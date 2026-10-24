# Parameters.scala：集中式设计参数

对应源码：[Parameters.scala](../../chisel_src/config/Parameters.scala)。包含 Parameters 固定合同、PEConfig 容量参数和 DesignConfig 顶层配置，不生成独立硬件 Module。

`PEConfig(h,q,e,alignWidth=40)` 直接描述一个 PE 每次接收的 H/Q/E 标量乘积数，避免从 family 字符串、全局环境变量、Group 数量反推能力。H/Q/E 分别是 BF16/FP16、MXFP8/6、MXFP4/NVFP4/HiF4 的共享运行模式，不能把三者相加作为同拍吞吐。

| 参数 | 合法范围 | 结构依据 |
| --- | --- | --- |
| h | 0 或 16 | H 模式每 packed word 一个元素 |
| q | 0 或 32 | Q 模式每 word 两个元素，32 元素共一个 MX scale block |
| e | 0、32 或 64 | E 模式每 word 四个元素；E32 只允许 H=Q=0 |
| alignWidth | 40–64 | 跨 scale 块固定点对齐窗口；默认保持源设计 W40 |

至少启用一个家族。允许 H+Q、H+E 等裁剪组合；E32 不与 H/Q 共用，是 8 个打包字的半尺寸 E-only PE。当前不假装支持任意 K；更大容量由 KPE 组合 1–4 个 PE，或后续另行设计。

派生关系：`words=max(h,q/2,e/4)` 为 8 或 16；`groups=words/4` 为 2 或 4。没有 H/Q 的 E-only 使用字级 W11、scale 后组级 W22；其他路径字级 W29、组级 W33。公共输出逻辑位宽 `resultWidth=alignWidth+2`，其中 magnitude 为 W−1 位、sign 单独一位。

`tag` 只表达容量；`subTag`、`groupTag` 表达 PE 内一个字、四个字的计算范围，不是模块层级。非默认对齐窗口增加 `_W<alignWidth>` 名称后缀，防止不同精度窗口被混认。

静态 `require` 对非法配置立即报错；没有复位、时钟、运行状态。需要审查的关键点是家族裁剪是否真正删除不需要的乘法器/对齐器，以及 E32 的 scale 调度是否与上游块划分一致。数值/面积验证待后续 SV/EDA 阶段。

## 生成时的配置入口

`DesignConfig(kind,pes)` 表达整个导出顶层。kind=mn 时 pes 只能有一个元素；kind=k 时有 1–4 个元素，所有 PE 对齐窗口一致。`topName` 自动由容量合计生成；完整有序布局保存在 JSON，避免名称相同而内部结构不同的配置碰撞。

`DesignConfig.load` 从版本化 JSON 读取参数，拒绝未知字段、非整数和非法组合。修改 [configs](../../configs/README.md) 中的文件，或运行时选择另一个文件即可生成新结构，无需改 PE.scala。参数在 elaboration 时生效，不是运行时寄存器；格式选择是另一个独立的事务控制。

`Parameters` 集中列出固定的 word/scale/anchor 位宽、保留位数和 11/18 拍流水合同。这些常量不是独立 DSE 旋钮，修改它们必须更新位宽证明、流水和 spec，不能像 h/q/e 一样任意扫描。
