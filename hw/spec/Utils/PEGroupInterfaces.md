# 分级PEGroup接口

对应源码：[PEGroupInterfaces.scala](../../chisel_src/Utils/PEGroupInterfaces.scala)。

仅供HQE/QE/E的PG数值边界：输入四对packed word，out_pegroup_anchor在S06发布signed W11 raw anchor，out_pegroup_data在S07发布signed局部和及special，两路间距1。

载体宽度依alignment和族派生，HQE/QE默认W33，E默认W22。raw anchor必须结合族I/F和bias转换；不能把不同族同宽数据当同一坐标。抽象PEGroupBase只维护形状与Valid接口，检查scale数和g0/g1关系，无独立实例。H/Q的原始乘积集合另用RawGroupIO，无本地求和。
