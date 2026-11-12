"""Render the DeepSeek precision mix and fastest DP ratio in one figure."""

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from ..common import digest, json_text, path_label, read_json, require
from .figures import MODELS, PAPER_WIDTH_IN, STYLE, load, save

PLANS = (
    ("expert_fp8", "Base"),
    ("expert_fp8+grouped_fp8", "O-down 8"),
    ("expert_fp8+grouped_fp4", "O-down 4"),
    ("expert_fp4", "Experts 4"),
    ("expert_fp4+grouped_fp4", "Both 4"),
    ("expert_fp4+grouped_fp4+linears_fp4+attention_fp8", "Aggressive"),
)
MIX = (
    ("bf16_macs", "BF16", "#74839a", ""),
    ("mxfp8_macs", "MXFP8", "#00717d", ""),
    ("mxfp4_macs", "MXFP4", "#d38361", "///"),
)
RATIO_COLORS = {
    "1:2:4": "#f1f2f4", "1:2:6": "#ffe5ba", "1:2:8": "#f6d6bf",
    "1:2:12": "#e6d9ef", "1:2:16": "#f5cad3",
    "1:4:4": "#cae5e8", "1:4:8": "#cee8d4",
    "1:6:12": "#deddf2", "1:8:16": "#f0ebcb",
}


def _work_mix(ax, cells):
    floor = [0.0] * len(cells)
    for key, _, color, hatch in MIX:
        shares = [100 * int(cell[key]) / int(cell["useful_macs"]) for cell in cells]
        ax.bar(range(len(cells)), shares, bottom=floor, width=0.65, color=color, hatch=hatch,
               edgecolor="#344454", linewidth=0.35)
        floor = [base + share for base, share in zip(floor, shares)]
    ax.set(ylim=(0, 104), yticks=(0, 50, 100))
    ax.tick_params(axis="x", bottom=False, labelbottom=False)


def _ratio_grid(ax, plan_rows, rates, anchor, show_plans):
    for y, bandwidth in enumerate(rates):
        for x, row in enumerate(plan_rows[bandwidth]):
            winner = row["winner_ratio"]
            fill = RATIO_COLORS[winner] if winner else "white"
            ax.add_patch(Rectangle((x - .5, y - .5), 1, 1, facecolor=fill, edgecolor="white", linewidth=1))
            near = row["runner_up_gap_pct"] and float(row["runner_up_gap_pct"]) < 1
            label = (winner + ("*" if near else "")) if winner else "–"
            ax.text(x, y, label, ha="center", va="center", fontsize=8.1, color="#202d38")
    if anchor in rates:
        ax.add_patch(Rectangle((-.5, rates.index(anchor) - .5), len(PLANS), 1, fill=False,
                               edgecolor="#536677", linewidth=.75, zorder=3, clip_on=False))
    ax.set(ylim=(-.5, len(rates) - .5), yticks=range(len(rates)), yticklabels=[f"{rate:g}" for rate in rates])
    ax.set_xticks(range(len(PLANS)), [label for _, label in PLANS])
    ax.tick_params(axis="x", bottom=False, labelbottom=show_plans, pad=4)
    ax.tick_params(axis="y", length=0, pad=3)
    for spine in ax.spines.values():
        spine.set_visible(False)


def run(run_dir, pdf, evidence, cap):
    manifest = read_json(run_dir / "manifest.json")
    rates = sorted(manifest["config"]["local_read_tb_s_per_core"])
    anchor = manifest["config"]["anchor_local_tb_s"]
    rows = load(run_dir, manifest, "selections.csv")
    plan_names = {plan for plan, _ in PLANS}
    caps = ("", float(cap))
    cells = {
        (row["model"], row["plan"], float(row["local_tb_s"]), float(row["cap_w"]) if row["cap_w"] else ""): row
        for row in rows if row["model"] in MODELS and row["plan"] in plan_names
        and (not row["cap_w"] or float(row["cap_w"]) == cap)
    }
    require(len(cells) == len(MODELS) * len(PLANS) * len(rates) * len(caps),
            "selected figure cohorts do not match the run's bandwidth and power-cap grid")

    plt.style.use(STYLE)
    fig = plt.figure(figsize=(PAPER_WIDTH_IN, 5.1), layout="constrained")
    layout = fig.add_gridspec(4, 2, height_ratios=(1.12, 2.18, 2.18, .28))
    exported = []
    for j, model in enumerate(MODELS):
        mix = fig.add_subplot(layout[0, j])
        mix.set(xlim=(-.5, len(PLANS) - .5), title=f"({chr(97 + j)}) {model.removeprefix('DeepSeek-')}")
        _work_mix(mix, [cells[model, plan, float(rates[0]), ""] for plan, _ in PLANS])
        mix.spines[["top", "right"]].set_visible(False)
        if j == 0:
            mix.set_ylabel("Useful MACs (%)")
        else:
            mix.tick_params(axis="y", labelleft=False)
        for i, budget in enumerate(caps, start=1):
            ax = fig.add_subplot(layout[i, j], sharex=mix)
            ax.set_title("Uncapped DP" if not budget else f"{budget:g} W DP cap", pad=5)
            plan_rows = {rate: [cells[model, plan, float(rate), budget] for plan, _ in PLANS] for rate in rates}
            _ratio_grid(ax, plan_rows, rates, anchor, show_plans=i == len(caps))
            if j == 0:
                ax.set_ylabel("Local read BW (TB/s)")
            else:
                ax.tick_params(axis="y", labelleft=False)
            exported.extend(row for entries in plan_rows.values() for row in entries)

    legend = fig.add_subplot(layout[3, :])
    legend.set_axis_off()
    handles = [Patch(facecolor=color, edgecolor="#344454", hatch=hatch, label=name) for _, name, color, hatch in MIX]
    handles.append(Line2D([], [], marker="$*$", linestyle="none", color="#202d38", label="<1% to runner-up"))
    legend.legend(handles=handles, loc="center", ncol=4, columnspacing=1.5)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    save(fig, pdf.parent, pdf.name)

    evidence.mkdir(parents=True, exist_ok=True)
    data = evidence / "figure_cells.csv"
    with data.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(exported)
    (evidence / "figure_manifest.json").write_text(json_text({
        "schema_version": 1, "plot_script": path_label(__file__), "plot_script_sha256": digest(__file__),
        "style_sha256": digest(STYLE), "matplotlib_version": matplotlib.__version__,
        "study_manifest_sha256": digest(run_dir / "manifest.json"),
        "study_selections_sha256": manifest["outputs_sha256"]["selections.csv"],
        "pdf": path_label(pdf), "pdf_sha256": digest(pdf), "figure_cells_sha256": digest(data),
        "workloads": MODELS, "plan_order": [plan for plan, _ in PLANS], "power_caps_w": [None, cap],
        "local_read_bandwidth_tb_s": rates, "highlighted_bandwidth_tb_s": anchor, "runner_up_marker_pct": 1,
    }) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--cap-w", type=float, default=150)
    args = parser.parse_args()
    try:
        run(args.run, args.pdf, args.evidence, args.cap_w)
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(2, f"migration_figure: {exc}\n")


if __name__ == "__main__":
    main()
