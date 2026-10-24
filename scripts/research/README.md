# Ascend Cube ISA 编译核验

这组工具只检查官方 Ascend C `Mmad` 的参数如何进入设备机器码，不实现本项目阵列，也不运行 GEMM。探针的 L0 输入未初始化，禁止执行其 kernel。

输入版本与官方下载地址见 [依赖记录](../../dependencies/ascend-research.json)，分析见 [官方源码与 ISA 报告](../../hw/spec/array_ref/ascend-official-mmad-isa-analysis.md)，精简结果见 [编译摘要](../../docs/research/ascend-mmad-isa/compile-summary.json)。

准备官方 BiSheng 编译器和匹配的 Ascend C 头文件。本轮从官方 CANN 9.1.0 Toolkit 仅提取 `cann-bisheng-compiler` 与 `cann-asc-devkit` 子包，校验子包 SHA-256 及其内置 payload SHA-256，解包到 `.deps/`，不运行安装器。官方Git标签v9.1.0用于样例/源码定位，官方9.1.0 release头文件用于编译；三个关键实现文件已与Git标签逐字节核对，hash见依赖记录。master的新类型与9.1.0编译器不兼容，不能替换这组固定输入。

在仓库根目录运行：

```bash
python3 scripts/research/inspect_ascend_mmad.py \
  --compiler .deps/cann-bisheng-compiler-9.1.0/extracted/tools/bisheng_compiler/bin/bisheng \
  --devkit .deps/cann-asc-devkit-9.1.0/extracted/x86_64-linux/asc \
  --output .cache/ascend-official/final-release-probes
```

也可将 `--devkit` 指向具备完整 Basic API 头文件依赖的官方源码 checkout；这是另一组输入，应重新运行并独立记录其 commit 与摘要。

脚本对16个形状生成设备 ELF、bitcode、LLVM IR、后端汇编和日志。它读取 ELF `.text`，按照官方 A2 opcode mask统计 MMAD 机器字，并核对IR中的实际M/K/N。汇编输出复用官方驱动的 target/LLVM 后端选项，要求从同一bitcode生成的 `.text` 与驱动原产物逐字节一致。普通 `llvm-objdump -d` 在本机显示 `<not available>`，不作为可读反汇编证据。

摘要中的 `fits_l0_capacity` 只检查文档描述的 A2/A3 普通稠密FP16→FP32容量，假定起始地址为0且没有其他存活张量。`checked_constraints_satisfied` 同时要求尺寸在合同内、编码保持原形状、三个L0容量满足；它不代表真实芯片验收。

K257、K512、K4095、K4096等案例刻意检查越界行为。编译器接受一个越界参数，或生成一条MMAD，都不能使该形状变成合法硬件负载。脚本从不执行设备产物。

输出写入显式给定目录；需要保留一批结果时应选用新目录，避免覆盖旧产物。原始对象文件及工具包不提交Git，提交探针、检查脚本、参数/版本/hash与小型摘要即可。
