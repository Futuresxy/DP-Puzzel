# DataUnpack_E：E 专用通路

对应源码：[DataUnpack_E.scala](../../../chisel_src/pe/PE_E/DataUnpack_E.scala)。来源/调整见 [六种PE设计](../../six-pe-design.md) 与 [固定版本指纹](../../six-pe-source.json)。

本文件拥有该族独立的选择/打包/寄存代码，未启用的格式分支从源码删除；原子解码函数共用DecodePrimitives，接口共用DecodeInterfaces。E/QE保留E8M0、E4M3、源E6M2及相应g0/g1处理。

Q/E/QE在S01寄存原始packed字并组合解码；固定寄存选择不是公共参数。Q尾数高lane在nibble2；FP6每byte低6bit；E四nibble，g0每word一bit、g1每两word一bit。非法有效输入断言，special分类包括元素/scale NaN、Inf和0×Inf。

待验收：全编码/scale边界、严重抵消/指数差、特殊值、连续/气泡/复位与模式合法性。当前定向smoke只覆盖−1/0/+1及合法unit scale的坐标和周期，不能标记完整精度passed；无PPA证据。
