import mill._
import mill.scalalib._

object pe extends ScalaModule {
  def scalaVersion = "2.13.12"
  def ivyDeps = Agg(ivy"org.chipsalliance::chisel:6.4.0",
    ivy"com.lihaoyi::os-lib:0.9.1", ivy"com.lihaoyi::ujson:3.1.0")
  def scalacPluginIvyDeps = Agg(ivy"org.chipsalliance:::chisel-plugin:6.4.0")
  override def sources = T.sources(millSourcePath / "chisel_src")
  override def millSourcePath = os.pwd
  override def scalacOptions = Seq("-deprecation", "-feature", "-unchecked", "-language:reflectiveCalls")
  override def forkArgs = Seq("-Xmx8G")
}
