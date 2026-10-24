# DataUnpack.scala：独立 A/B 解包与特殊值分类

对应源码：[DataUnpack.scala](../../chisel_src/pe/DataUnpack.scala)。源文件、固定 commit、迁移调整见 [迁移说明](../full-reuse-migration.md) 和 [指纹清单](../full-reuse-source.json)。

一个 Full PEGroup 的4对 packed word共享这一个解包 Module，先按 A/B 各自原始 dtype/scale 解码，不能用 canonical product type 重解码两侧。Full 实例固定 registeredOutput=true、compactInputRegister=false，于 S01 输出已解码字段；其他源开关保留为局部构造能力，本轮配置不开放。

H：FP16 hidden+fraction+pad 为12bit，BF16为8bit；subnormal 用有效指数1且 hidden0。Q：每 W16 word 包含两个8bit存储槽，FP6放每槽低6位；统一成 E5指数和4bit尾数；高 lane 尾数放 nibble2，以匹配源 SubPE。E：四个 nibble，E2M1 把指数融入4bit尾数，HiF4结合g0/g1实验编码。输出 exp/mant/sign为W10/W16/W4。

scale 统一成 W8 bias127指数和 W4 UQ1.3 尾数。H 使用unit并忽略传入scale数据。E8M0全一为NaN；E4M3 scale看低7bit，0x7f为NaN、0x78..0x7e有限；HiF4 E6M2 bias48且0xff为NaN，具体外部规范待确认。元素 E4M3仅最大幅度码NaN，E5M2/H有Inf/NaN，FP6/E2M1为有限编码。zero×Inf 以及scale/element特殊值先形成逐lane flags，再合并到PG sideband，数值路径使用有限安全占位。

Valid-only，合法输入II=1/延迟1；非法格式/scale应断言，不能静默认为接收成功。输出不接受反压。valid同步清零，decoded数据RegEnable保持不复位。Bundle与unpack函数在本文件同路径记录，不增加独立硬件Module。

待 SV 穷举小格式编码、subnormal、FP6 padding、Q nibble2、E4M3有限上界、scale zero/NaN、0×Inf、混合A/B和连续/气泡/复位。来源工程结果不继承为本项目验收。
