"""Render vector figures from one verified DSE result directory."""

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from ..common import ROOT, digest, json_text, path_label, read_json, require

MODELS = ("DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash")
PLANS = ("expert_fp8", "expert_fp4")
RATIOS = ("1:2:4", "1:2:6", "1:2:8", "1:4:4", "1:4:8", "1:2:12", "1:2:16", "1:6:12", "1:8:16")
TOPOLOGY = "sm_4x16x4"
COLORS = ("#00717d", "#c04829", "#3e5b93", "#774b75")
PLAN_LABELS = ("W4A8 via MXFP8", "Routed W4A4 via MXFP4")
PAPER_WIDTH_IN = 7.16
STYLE = ROOT / ".skill/academic-figures/assets/paper.mplstyle"


def subset(rows, **fields):
    return [row for row in rows if all(row[key] == str(value) for key, value in fields.items())]


def load(run, manifest, name):
    path = run / name
    require(digest(path) == manifest["outputs_sha256"][name], f"Changed study output {name}")
    with path.open(newline="") as source:
        return list(csv.DictReader(source))


def anchor(rows, **extra):
    return subset(rows, tokens=2048, batch=1, topology=TOPOLOGY, **extra)


def save(fig, output, name):
    fig.savefig(output / name, bbox_inches="tight", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def bandwidth_figure(rows, output):
    fig, axes = plt.subplots(2, 2, figsize=(PAPER_WIDTH_IN, 5.5), sharex=True, sharey=True, layout="constrained")
    for i, model in enumerate(MODELS):
        for j, plan in enumerate(PLANS):
            ax = axes[i, j]
            items = anchor(rows, view="chip_selection", model=model, plan=plan)
            budgets = sorted({float(row["local_tb_s"]) for row in items})
            index = {(row["ratio"], float(row["local_tb_s"])): row for row in items}
            best_t = [min(RATIOS, key=lambda r: float(index[r, bw]["seconds"])) for bw in budgets]
            best_e = [min(RATIOS, key=lambda r: float(index[r, bw]["dp_energy_j"])) for bw in budgets]
            relative = [[100 * (float(index[r, bw]["seconds"]) / float(index[best_t[k], bw]["seconds"]) - 1)
                         for k, bw in enumerate(budgets)] for r in RATIOS]
            heat = ax.pcolormesh([x - 0.5 for x in range(len(budgets) + 1)],
                                 [y - 0.5 for y in range(len(RATIOS) + 1)], relative,
                                 vmin=0, vmax=70, cmap="YlOrBr", rasterized=False)
            ax.scatter(range(len(budgets)), [RATIOS.index(r) for r in best_t],
                       marker="o", s=46, facecolor="none", edgecolor="#263c52", linewidth=1.35)
            ax.scatter(range(len(budgets)), [RATIOS.index(r) for r in best_e],
                       marker="+", s=32, color="#263c52", linewidth=1.2)
            ax.set_xticks(range(len(budgets)), [f"{bw:g}" for bw in budgets])
            ax.set_yticks(range(len(RATIOS)), RATIOS)
            ax.set_ylim(len(RATIOS) - .5, -.5)
            ax.set_title(f"{model.removeprefix('DeepSeek-')} · {'W4A8' if j == 0 else 'W4A4'}")
    scale = fig.colorbar(heat, ax=axes, label="Latency above fastest (%)", extend="max", shrink=0.83)
    scale.solids.set_rasterized(False)
    fig.supxlabel("Local read bandwidth per SM (TB/s)", fontsize=9)
    fig.supylabel("DP compute ratio (BF16:MXFP8:MXFP4)", fontsize=9)
    save(fig, output, "bandwidth_rank.pdf")


def power_figure(rows, output):
    fig, axes = plt.subplots(1, 2, figsize=(PAPER_WIDTH_IN, 3.35), layout="constrained")
    ax, trade = axes
    for index, plan in enumerate(PLANS):
        items = anchor(rows, view="power_cap", model=MODELS[1], plan=plan)
        caps = sorted({int(row["cap_w"]) for row in items})
        winners = [min(subset(items, cap_w=cap), key=lambda row: float(row["seconds"])) for cap in caps]
        ax.plot(caps, [1e3 * float(row["seconds"]) for row in winners], marker=("o", "s")[index],
                linestyle=("-", "--")[index], color=COLORS[index], label=("W4A8", "W4A4")[index])
        previous = None
        for cap, row in zip(caps, winners):
            if previous != row["ratio"]:
                offset = (5, 8) if index == 0 else (5, -12)
                ax.annotate(row["ratio"], (cap, 1e3 * float(row["seconds"])), xytext=offset,
                            textcoords="offset points", fontsize=8, color=COLORS[index])
            previous = row["ratio"]
    ax.set(xlabel="DP budget proxy (W)", ylabel="GEMM time (ms)", title="V4.1 · DP budget sweep")
    ax.margins(y=0.14)
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.24)

    items = anchor(rows, view="chip_selection", model=MODELS[1], plan=PLANS[1], local_tb_s=4)
    points = trade.scatter([float(row["seconds"]) * 1e3 for row in items],
                           [float(row["dp_energy_j"]) for row in items],
                           c=[float(row["dp_envelope_w"]) for row in items], cmap="viridis", s=55)
    labels = {"1:2:4": (6, 6), "1:8:16": (-34, -12), "1:4:8": (-6, -12)}
    for row in items:
        if row["ratio"] in labels:
            trade.annotate(row["ratio"], (float(row["seconds"]) * 1e3, float(row["dp_energy_j"])),
                           xytext=labels[row["ratio"]], textcoords="offset points", fontsize=8)
    trade.margins(x=0.13, y=0.20)
    trade.set(xlabel="GEMM time (ms)", ylabel="DP energy proxy (J)", title="V4.1 · routed W4A4")
    trade.grid(alpha=0.24)
    scale = fig.colorbar(points, ax=trade, label="DP envelope (W)", shrink=0.8)
    scale.solids.set_rasterized(False)
    save(fig, output, "power_energy_tradeoff.pdf")


def migration_figure(migrations, rows, output):
    fig = plt.figure(figsize=(PAPER_WIDTH_IN, 3.55), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=(1, 0.13))
    axes = [fig.add_subplot(grid[0, column]) for column in range(2)]
    legend = fig.add_subplot(grid[1, :])
    legend.set_axis_off()
    ratio_label = "1:8:16"
    singles = {
        "expert_fp4": ("Routed experts → FP4", COLORS[0]),
        "expert_fp8+grouped_fp4": ("Grouped O-down → FP4", COLORS[1]),
        "expert_fp8+linears_fp4": ("Linears / shared FFN → FP4", COLORS[2]),
        "expert_fp8+attention_fp8": ("Main attention → FP8", COLORS[3]),
    }
    baselines = {row["candidate_id"]: row for row in rows if row["view"] == "model_adaptation"}
    for ax, model in zip(axes, MODELS):
        cohort = anchor(migrations, model=model, ratio=ratio_label, local_tb_s=4)
        for row in cohort:
            base = baselines[row["baseline_id"]]
            x = int(row["migrated_useful_macs"]) / int(base["useful_macs"])
            style = singles.get(row["plan"])
            ax.scatter(x, float(row["conversion_break_even_s"]) * 1e3,
                       c=style[1] if style else "#8b99a5", alpha=1 if style else 0.7,
                       marker="D" if style else "o", s=38 if style else 21)
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set(xlim=(0, 1.03), ylim=(0, 165), title=model.removeprefix("DeepSeek-"),
               xlabel="Useful GEMM MACs reassigned")
        ax.grid(alpha=0.24)
    axes[0].set_ylabel("Modeled time saved before conversion (ms)")
    markers = [plt.Line2D([], [], color=color, marker="D", linestyle="none", markersize=5, label=label)
               for label, color in singles.values()]
    legend.legend(handles=markers, loc="center", ncol=2, frameon=False, fontsize=8)
    save(fig, output, "precision_migration.pdf")


def robustness_figure(rows, output):
    fig, axes = plt.subplots(1, 2, figsize=(PAPER_WIDTH_IN, 3.5), sharey=True, layout="constrained")
    for ax, plan, title in zip(axes, PLANS, PLAN_LABELS):
        cohort = {row["ratio"]: row for row in subset(rows, plan=plan)}
        lat = [100 * float(cohort[r]["max_latency_regret"]) for r in RATIOS]
        ene = [100 * float(cohort[r]["max_energy_regret"]) for r in RATIOS]
        loc = range(len(RATIOS))
        ax.barh([x - .19 for x in loc], lat, height=.35, color=COLORS[0], label="Latency")
        ax.barh([x + .19 for x in loc], ene, height=.35, color=COLORS[1],
                edgecolor="#572d23", linewidth=.35, hatch="//", label="DP energy")
        ax.set(yticks=loc, yticklabels=RATIOS, xlim=(0, 77), title=title, xlabel="Worst-case regret (%)")
        ax.grid(axis="x", alpha=.25)
    axes[0].invert_yaxis()
    axes[1].legend(frameon=False, fontsize=8)
    save(fig, output, "worst_case_regret.pdf")


def run(run_dir, output):
    plt.style.use(STYLE)
    matplotlib.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "axes.spines.top": False,
                                "axes.spines.right": False, "axes.titleweight": "bold",
                                "axes.axisbelow": True})
    manifest = read_json(run_dir / "manifest.json")
    rows = load(run_dir, manifest, "candidate_evaluations.csv")
    migrations = load(run_dir, manifest, "precision_migrations.csv")
    robustness = load(run_dir, manifest, "robustness.csv")
    output.mkdir(parents=True, exist_ok=True)
    bandwidth_figure(rows, output)
    power_figure(rows, output)
    migration_figure(migrations, rows, output)
    robustness_figure(robustness, output)
    for name in ("bandwidth_boundaries.csv", "robustness.csv", "validation.json"):
        require(digest(run_dir / name) == manifest["outputs_sha256"][name], f"Changed study output {name}")
        (output / name).write_text((run_dir / name).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    evidence = [row for row in rows if row["tokens"] == "2048" and row["batch"] == "1"
                and row["local_tb_s"] == "4" and (
                    row["view"] in {"chip_selection", "compute_only", "isolated_weights", "single_context",
                                    "shared_b_broadcast", "idle_10pct", "power_cap"}
                    or row["view"] == "model_adaptation" and row["ratio"] == "1:8:16")]
    with (output / "anchor_evidence.csv").open("w", newline="", encoding="utf-8") as stream:
        columns = ("candidate_id", "workload_id", "model", "schedule", "view", "topology", "ratio", "plan",
                   "plan_id", "deployment_id", "local_tb_s", "cap_w", "cores", "contexts", "partition",
                   "useful_macs", "issued_macs", "ab_bytes", "d_bytes", "seconds", "ideal_s", "compute_s",
                   "read_s", "write_s", "dp_average_w", "dp_envelope_w", "dp_energy_j", "quality_status")
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(evidence)
    (output / "figure_manifest.json").write_text(json_text({
        "schema_version": 1, "plot_script": path_label(__file__), "plot_script_sha256": digest(__file__),
        "plot_style": path_label(STYLE), "plot_style_sha256": digest(STYLE),
        "matplotlib_version": matplotlib.__version__,
        "study_manifest_sha256": digest(run_dir / "manifest.json"),
        "source_outputs_sha256": manifest["outputs_sha256"],
        "figure_sha256": {path.name: digest(path) for path in sorted(output.glob("*.pdf"))},
        "table_sha256": {path.name: digest(path) for path in sorted(output.glob("*.csv"))},
        "selection": {"tokens": 2048, "batch": 1, "topology": TOPOLOGY, "local_tb_s": 4},
    }) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.run, args.output)


if __name__ == "__main__":
    main()
