package dp.elaborate

import circt.stage.ChiselStage
import dp.config.DesignConfig
import java.security.MessageDigest
import java.time.{Instant, ZoneOffset}
import java.time.format.DateTimeFormatter

/** Parameter-file driven canonical RTL export; never declares verification passed. */
object Generate {
  private def sha256(bytes: Array[Byte]): String =
    MessageDigest.getInstance("SHA-256").digest(bytes).map(b => f"${b & 0xff}%02x").mkString
  private def hashText(text: String): String = sha256(text.getBytes("UTF-8"))

  def main(args: Array[String]): Unit = {
    require(args.length == 2, "Usage: pe.runMain dp.elaborate.Generate <config.json> <export-reason>")
    val hw = os.pwd
    require(os.isDir(hw / "chisel_src") && os.isFile(hw / "build.sc"), "Run from the hw directory")
    val config = DesignConfig.load(os.Path(args(0), hw))
    require(args(1).trim.nonEmpty, "Every export requires a reason")
    val firtoolDir = sys.env.getOrElse("CHISEL_FIRTOOL_PATH",
      throw new IllegalArgumentException("Set CHISEL_FIRTOOL_PATH to the directory containing firtool 1.62.0"))
    val firtool = os.Path(firtoolDir, hw) / "firtool"
    val toolVersion = os.proc(firtool.toString, "--version").call().out.text().trim
    require(toolVersion.contains("firtool-1.62.0"), "This build pins firtool 1.62.0")

    def sources: Seq[(String, String)] = {
      val files = os.walk(hw / "chisel_src").filter(p => os.isFile(p) && p.ext == "scala") ++
        Seq(hw / "build.sc", hw / ".mill-version")
      files.sortBy(_.toString).map(p => p.relativeTo(hw).toString -> sha256(os.read.bytes(p)))
    }
    val sourceFiles = sources
    val sourceHash = hashText(sourceFiles.map { case (path, hash) => s"$path $hash" }.mkString("\n"))
    val configText = ujson.write(config.json)
    val configId = s"${config.kind}-${hashText(configText).take(12)}"
    val now = Instant.now()
    val stamp = DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmssSSSSSS'Z'").withZone(ZoneOffset.UTC).format(now)
    val exportId = s"${config.topName}__${configId}__${stamp}__${sourceHash.take(12)}"
    val directory = hw / "rtl" / exportId
    require(!os.exists(directory), "Refusing to overwrite an existing RTL export")
    val gitCommit = os.proc("git", "rev-parse", "HEAD").call(cwd = hw).out.text().trim
    val dirty = os.proc("git", "status", "--porcelain").call(cwd = hw).out.text().nonEmpty
    val command = Seq("mill", "-i", "pe.runMain", "dp.elaborate.Generate", args(0), args(1))
    val flags = Array("--disable-all-randomization", "--strip-debug-info")
    val manifest = ujson.Obj(
      "schema_version" -> 1, "export_id" -> exportId, "top" -> config.topName,
      "created_utc" -> now.toString, "reason" -> args(1), "state" -> "generating",
      "config_id" -> configId, "parameters" -> config.json, "git_commit" -> gitCommit,
      "git_dirty" -> dirty, "source_sha256" -> sourceHash,
      "sources" -> ujson.Arr.from(sourceFiles.map { case (path, hash) => ujson.Obj("path" -> path, "sha256" -> hash) }),
      "tools" -> ujson.Obj("mill" -> "0.11.8", "scala" -> "2.13.12", "chisel" -> "6.4.0", "firtool" -> toolVersion),
      "command" -> ujson.Arr.from(command), "chisel_options" -> ujson.Arr("--split-verilog", "--warnings-as-errors"),
      "firtool_options" -> ujson.Arr.from(flags),
      "validation" -> ujson.Obj("rtl_test" -> "not_run", "ppa_eligible" -> false))
    os.makeDir.all(directory / "src")
    def record(state: String): Unit = {
      manifest("state") = state
      os.write.over(directory / "manifest.json", ujson.write(manifest, indent = 2) + "\n")
      os.write.over(directory / "README.md",
        s"# $exportId\n\nTime (UTC): $now\n\nReason: ${args(1)}\n\n" +
        s"State: **$state**. RTL test: **not_run**. PPA eligible: **false**.\n\n" +
        s"Source SHA-256: $sourceHash; Git: $gitCommit; dirty: $dirty.\n\n" +
        "Parameters, tool versions, command, source hashes and module mapping: [manifest.json](manifest.json).\n" +
        "Use files.f from this directory; do not copy RTL into test/DC/power directories.\n")
    }
    record("generating")
    try {
      ChiselStage.emitSystemVerilogFile(Elaborate.module(config),
        args = Array("--target-dir", (directory / "src").toString, "--split-verilog", "--warnings-as-errors"), firtoolOpts = flags)
      require(sources == sourceFiles, "Sources changed during export; discard this inconsistent export")
      val rtl = os.walk(directory / "src").filter(p => os.isFile(p) && p.ext == "sv").sortBy(_.toString)
      require(rtl.nonEmpty, "No SystemVerilog files emitted")
      val modulePattern = "(?m)^\\s*module\\s+([A-Za-z_][A-Za-z_0-9$]*)\\b".r
      val modules = rtl.map { path =>
        val names = modulePattern.findAllMatchIn(os.read(path)).map(_.group(1)).toVector
        require(names.size == 1 && path.last == s"${names.head}.sv",
          s"Expected one same-named module in ${path.last}; found ${names.mkString(",")}")
        val name = names.head
        val source = if (name.startsWith("K_PE_")) "core/KPE.scala"
          else if (name.startsWith("MN_PE_")) "core/MNPE.scala"
          else if (name.startsWith("PE_")) "pe/PE.scala"
          else if (name == "Fp32Pack") "common/Fp32Pack.scala"
          else throw new IllegalArgumentException(s"Unmapped generated module $name")
        ujson.Obj("module" -> name, "chisel_source" -> s"hw/chisel_src/$source",
          "path" -> path.relativeTo(directory).toString, "sha256" -> sha256(os.read.bytes(path)))
      }
      require(modules.exists(_("module").str == config.topName), "Configured top is missing")
      // Drop only compiler intermediates inside this new export; keep headers/auxiliary inputs.
      os.walk(directory / "src").filter(p => os.isFile(p) &&
        (p.ext == "fir" || p.last.endsWith(".anno.json") || p.last == "filelist.f")).foreach(os.remove(_))
      val files = os.walk(directory / "src").filter(os.isFile(_)).sortBy(_.toString)
      manifest("modules") = ujson.Arr.from(modules)
      manifest("files") = ujson.Arr.from(files.map(p => ujson.Obj(
        "path" -> p.relativeTo(directory).toString, "sha256" -> sha256(os.read.bytes(p)))))
      val filelist = "+incdir+src\n" + rtl.map(_.relativeTo(directory).toString).mkString("\n") + "\n"
      os.write(directory / "files.f", filelist)
      manifest("filelist_sha256") = hashText(filelist)
      record("generated")
      println(s"Generated ${directory.relativeTo(hw / os.up)}; RTL validation not run")
    } catch {
      case error: Exception =>
        os.remove.all(directory / "src")
        if (os.exists(directory / "files.f")) os.remove(directory / "files.f")
        manifest("error") = error.toString
        record("failed")
        throw error
    }
  }
}
