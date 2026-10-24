# Parameters.scala：固定编码、位宽与周期

对应源码：[Parameters.scala](../../chisel_src/config/Parameters.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

`Resource` 固定一组四 word、一个 MidGroup 十六 word。真正可调的顶层由本文件的 DesignConfig 从 JSON 读取，不使用 CFG_* 环境变量决定电路。`Design` 固定 exp/mant/sign=10/16/4、SubPE W29、Q retain W28、组内 pad2、anchor W11、最终 mantissa W26，默认跨组窗口 W40。窗口的实际值通过 PETile/MidGroup 构造参数传递，不能改默认常量冒充配置。

格式 W4 编码沿用源工程：NVFP4=0、E2M1=1、HiF4=2、E2M3=3、E3M2=4、E4M3=5、E5M2=6、BF16=7、FP16=8。9..14 为保留旧编码，当前 full 不支持整数/FP32/TF32 A/B。C W2 编码 FP32=0、FP16=1、BF16=2。Scale W2：NONE=0、E4M3=1、E8M0=2、E6M2=3。

bias：FP32/BF16/E8=127，FP16/E5=15，E4=7、E3=3、E2=1；源 HiF4 scale E6 bias=48。FPMAX 为全一指数码界限，不代表所有格式都把该指数视为 Inf。特殊值规则由解包决定。

`PETilePipeline` 约束 SubPE3、PG anchor/data 间距1、PG7、Mid11、C unpack2、raw C延迟9、最终18。它们是固定合同而非 sweep 参数。该文件只创建 Scala 常量和 Chisel 字面量，无独立 Module、寄存器、延迟或复位。待验证编码与每个使用点保持一致，修改固定合同需重新做位宽审查和 RTL 验收。

## 唯一可调配置

`DesignConfig(midGroups=1,alignWidth=40)` 为不可变case class。mid_groups=1..4，align_width=40..64；wordCount=16*midGroups，H/Q/E容量自动推导为wordCount/2wordCount/4wordCount。非法范围由require拒绝，默认W40不加后缀，其余加_W…。

JSON只允许schema_version=1、mid_groups、align_width三个字段，值必须是Int范围内的整数。fromJson/load拒绝未知字段、旧kind/pes schema和非整数。配置不含运行模式，模式来自batch cfg；同一窗口用于全部MidGroup与C/D。旧PEConfig及mn/k配置已移除。

这些参数在elaboration时决定电路；数值编码、局部W29/W33、anchor和流水不是独立调参项。此文件无独立Module或复位状态。
