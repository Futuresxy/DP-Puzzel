"""Model four cumulative prefill precision choices on the legacy PETile candidates."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from costs import mapped_work
from import_petile17_n12 import write_csv
from plot_triangles import draw_petile17_regions, plt, style_petile17
from simplex import HEIGHT, xy
from workloads import SOURCE, v41

PAPER = Path(__file__).resolve().parents[1]
RESULTS = Path("data/results/petile17_n12")
STEM = "petile17_precision_migration"
STAGES = (
    ("W4A4 routed experts", "#223c5a", "o"),
    ("Q/O projections + shared experts to FP4", "#87519a", "s"),
    ("Main SWA/CSA to FP8", "#237b73", "^"),
    ("Main SWA/CSA to FP4", "#aa5b28", "D"),
)
MAIN_V4 = ("attention.qk", "attention.pv")
MAIN_V41 = ("swa.qk", "swa.pv", "global.qk", "global.pv")
PRECISION_AXIS = {"bf16": 0, "mxfp8_e4m3": 1, "mxfp4_e2m1": 2, "nvfp4": 2}
PROJECTIONS = ("q_down", "q_up", "o_final")
LINEAR_FP4 = ("o_group", *PROJECTIONS, "moe.shared.gate", "moe.shared.up", "moe.shared.down")


def precision_stages(model, context, batch):
    """Conserve useful FLOPs while remapping explicitly selected operations."""
    _, excluded, ledger = mapped_work(model, "prefill", context, "nvfp4_experts", batch)
    config = json.loads((SOURCE/model/"inference/config.json").read_text())
    is_v41 = model == "DeepSeek-V4.1-Flash"
    main = MAIN_V41 if is_v41 else MAIN_V4
    # The V4 workload ledger aggregates SWA and global attention per layer.
    # HCA's r=128 global part stays BF16; the local SWA part still migrates.
    hca_flops_per_op = (0 if is_v41 else 2 * batch * config["n_heads"] * config["head_dim"]
                        * v41.visible_pairs(0, context, 128))
    hqe = [0, 0, 0]
    moved = dict(grouped_o_down_flops=0, q_down_up_o_up_flops=0, shared_expert_flops=0,
                 main_swa_csa_flops=0, retained_hca_flops=0)
    for row in ledger:
        kernel, work, fmt = row["kernel"], row["flops"], row["format"]
        if fmt == "FP32_excluded":
            continue
        hqe[PRECISION_AXIS[fmt]] += work
        if kernel in LINEAR_FP4:
            expected = "bf16" if kernel == "o_group" else "mxfp8_e4m3"
            if fmt != expected:
                raise ValueError(f"{model}/{kernel} should start in {expected}, got {fmt}")
            if kernel == "o_group":
                moved["grouped_o_down_flops"] += work
            elif kernel in PROJECTIONS:
                moved["q_down_up_o_up_flops"] += work
            else:
                moved["shared_expert_flops"] += work
        if kernel in main:
            if fmt != "bf16":
                raise ValueError(f"{model}/{kernel} should start in BF16, got {fmt}")
            hca = hca_flops_per_op if not is_v41 and config["compress_ratios"][row["layer_id"]] == 128 else 0
            if hca > work:
                raise ValueError(f"{model}/{kernel} contains less work than its HCA global component")
            moved["retained_hca_flops"] += hca
            moved["main_swa_csa_flops"] += work - hca

    h, q, e = hqe
    from_h = moved["grouped_o_down_flops"]
    from_q = moved["q_down_up_o_up_flops"] + moved["shared_expert_flops"]
    attention = moved["main_swa_csa_flops"]
    if not all(value > 0 for value in (from_h, from_q, attention)):
        raise ValueError(f"{model}/{context} does not cover all migration groups")
    stages = [
        (h, q, e),
        (h-from_h, q-from_q, e+from_h+from_q),
        (h-from_h-attention, q-from_q+attention, e+from_h+from_q),
        (h-from_h-attention, q-from_q, e+from_h+from_q+attention),
    ]
    if any(sum(point) != sum(hqe) or min(point) < 0 for point in stages):
        raise ValueError(f"{model}/{context} did not conserve H/Q/E work")
    if sum(hqe) + excluded != sum(row["flops"] for row in ledger):
        raise ValueError(f"{model}/{context} did not conserve useful GEMM work")
    return stages, excluded, moved


def evaluate_migration(deployment):
    ratios = deployment["ratios"]
    coefficients = np.asarray(deployment["time_coefficients"], dtype=float)
    if coefficients.shape != (len(ratios), 3) or not np.all(np.isfinite(coefficients) & (coefficients > 0)):
        raise ValueError("Deployment must provide positive H/Q/E time coefficients for each ratio")
    cfg = deployment["configuration"]
    points, evaluations = [], []
    for model in cfg["models"]:
        for context in cfg["contexts"]:
            stages, excluded, moved = precision_stages(model, context, cfg["batch"])
            seconds = np.asarray(stages) @ coefficients.T / 1e12
            baseline = seconds[0].min()
            for stage, (flops, times) in enumerate(zip(stages, seconds)):
                total = sum(flops)
                fastest = "|".join(r for r, value in zip(ratios, times)
                                   if np.isclose(value, times.min(), rtol=1e-10, atol=0))
                point_id = f"{model}/prefill/{context}/stage{stage}"
                points.append(dict(point_id=point_id, model=model, phase="prefill",
                                   context_tokens=context, batch=cfg["batch"], stage=stage,
                                   stage_label=STAGES[stage][0],
                                   x_H=flops[0]/total, x_Q=flops[1]/total, x_E=flops[2]/total,
                                   H_flops=flops[0], Q_flops=flops[1], E_flops=flops[2],
                                   total_hqe_flops=total, excluded_FP32_flops=int(excluded),
                                   hqe_coverage=total/(total+excluded), **moved,
                                   fastest=fastest, time_s=float(times.min()),
                                   time_over_w4a4=float(times.min()/baseline)))
                evaluations.extend(dict(point_id=point_id, ratio=ratio, time_s=float(value))
                                   for ratio, value in zip(ratios, times))
    return points, evaluations


def write_compact_table(path, points, context):
    rows = [
        "% Generated by scripts/precision_migration.py.",
        r"\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}llccc@{}}\toprule",
        r"Model & Step & $x_H/x_Q/x_E$ (\%) & Best ratio & $T^*/T^*_0$ \\\midrule",
    ]
    for point in points:
        if point["context_tokens"] != context:
            continue
        model = point["model"].removeprefix("DeepSeek-") if point["stage"] == 0 else ""
        shares = "/".join(f"{100*point[f'x_{family}']:.2f}" for family in "HQE")
        ratio = point["fastest"].replace("|", r"\,/\,")
        rows.append(f"{model} & {point['stage']} & {shares} & ${ratio}$ & {point['time_over_w4a4']:.3f}" + r" \\")
        if point["stage"] == len(STAGES)-1:
            rows.append(r"\addlinespace[2pt]")
    rows.extend((r"\bottomrule\end{tabular*}", ""))
    path.write_text("\n".join(rows))


def draw_zoom(points, deployment, output):
    """Crop all three ternary panels to a common range around the trajectories."""
    style_petile17()
    coords = xy([[row[f"x_{family}"] for family in "HQE"] for row in points])
    xlim = (max(0, coords[:, 0].min()-.045), min(1.01, coords[:, 0].max()+.045))
    ylim = (-.006, min(HEIGHT, coords[:, 1].max()+.035))
    cfg = deployment["configuration"]
    models = cfg["models"]
    fig, axes = plt.subplots(1, len(models), figsize=(7.2, 2.2), squeeze=False)
    for ax, model in zip(axes[0], models):
        draw_petile17_regions(ax, deployment["time_regions"], deployment["ratios"], labels=False)
        for family in (0, 2):
            other = [i for i in range(3) if i != family]
            for value in np.arange(.05, 1, .05):
                endpoints = np.zeros((2, 3))
                endpoints[:, family] = value
                endpoints[0, other[0]] = 1-value
                endpoints[1, other[1]] = 1-value
                ax.plot(*xy(endpoints).T, color="#687583", lw=.3, alpha=.4, zorder=2)
        border = xy([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]])
        ax.plot(*border.T, color="#34404a", lw=.7, zorder=3)
        ends = []
        for stage, (label, color, marker) in enumerate(STAGES):
            rows = [r for r in points if r["model"] == model and r["stage"] == stage]
            trace = xy([[r[f"x_{family}"] for family in "HQE"] for r in rows])
            ax.plot(*trace.T, color=color, marker=marker, mfc="white", ms=3, mew=.7, lw=.9,
                    label=f"{stage}  {label}", zorder=5)
            ax.plot(*trace[-1], marker=marker, color=color, mfc=color, ms=5, mew=.65, zorder=7)
            ends.append(trace[-1])
        for start, end in zip(ends, ends[1:]):
            ax.annotate("", xy=end, xytext=start,
                        arrowprops=dict(arrowstyle="->", color="#46515b", lw=.75,
                                        shrinkA=4, shrinkB=4, mutation_scale=8), zorder=6)
        h_ticks = [p for p in range(0, 101, 5) if ylim[0] <= HEIGHT*p/100 <= ylim[1]]
        e_ticks = [p for p in range(0, 101, 10) if xlim[0] <= p/100 <= xlim[1]]
        ax.set(xlim=xlim, ylim=ylim, aspect="equal",
               xticks=[p/100 for p in e_ticks], xticklabels=e_ticks,
               yticks=[HEIGHT*p/100 for p in h_ticks], yticklabels=h_ticks,
               title=model.removeprefix("DeepSeek-"))
        ax.set_anchor("S")
        ax.set_xlabel("E FLOP share (%)", labelpad=2)
        ax.tick_params(length=2, width=.55, labelsize=7, pad=2)
        ax.spines[["right", "top"]].set_visible(False)
    axes[0][0].set_ylabel("H FLOP share (%)", labelpad=2)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="lower center", bbox_to_anchor=(.5, .01),
               fontsize=7.6, frameon=False, columnspacing=1.5)
    fig.subplots_adjust(left=.067, right=.995, bottom=.36, top=.97, wspace=.26)
    fig.savefig(output/f"{STEM}.pdf", bbox_inches="tight", pad_inches=.04,
                metadata={"CreationDate": None})
    fig.savefig(output/f"{STEM}.png", dpi=400, bbox_inches="tight", pad_inches=.04)
    plt.close(fig)


def run(deployment_path, output):
    deployment = json.loads(deployment_path.read_text())
    points, evaluations = evaluate_migration(deployment)
    data, figures, tables = output/RESULTS, output/"figures", output/"tables"
    for folder in (data, figures, tables):
        folder.mkdir(parents=True, exist_ok=True)
    write_csv(data/"precision_migration_points.csv", points)
    write_csv(data/"precision_migration_evaluations.csv", evaluations)
    context = deployment["configuration"]["contexts"][-1]
    write_compact_table(tables/f"{STEM}_table.tex", points, context)
    draw_zoom(points, deployment, figures)
    inputs = [deployment_path, Path(__file__), PAPER/"scripts/costs.py", PAPER/"scripts/workloads.py",
              PAPER/"scripts/deepseek_v41.py", PAPER/"scripts/plot_triangles.py", PAPER/"scripts/simplex.py",
              PAPER/"scripts/import_petile17_n12.py"]
    inputs += [SOURCE/model/"inference/config.json" for model in deployment["configuration"]["models"]]
    manifest = dict(
        status="analytical_uncalibrated",
        scope="cold prefill, useful GEMM service time at fixed whole-core area",
        stages=[label for label, _, _ in STAGES],
        compact_table_context=context, points=len(points), evaluations=len(evaluations),
        zoom_markers="Open markers show earlier context samples. Filled markers and arrows show the longest context.",
        attention_scope={
            "V4": "all local SWA and r=4 CSA main QK/PV, excluding r=128 HCA global QK/PV",
            "V4.1": "local SWA and all CSA2 global main QK/PV in existing CED schedule",
        },
        attention_sources=[
            "https://arxiv.org/html/2606.19348v1#S4.SS2.SSS1",
            "https://arxiv.org/html/2609.19969v1",
        ],
        assumption="Only the stated multiply precision changes; FLOPs, shapes, model schedule and excluded FP32 work are conserved.",
        limits="Hypothetical precision eligibility; quality, conversion, utilization, memory, power and whole-model latency are not evaluated.",
        inputs={str(path.relative_to(PAPER)) if path.is_relative_to(PAPER) else path.name:
                hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
    )
    (data/"precision_migration_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(f"Evaluated {len(points)} migration points over {len(deployment['ratios'])} candidate ratios")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", type=Path, default=PAPER/RESULTS/"deployment.json")
    parser.add_argument("--output", type=Path, default=PAPER)
    args = parser.parse_args()
    run(args.deployment.resolve(), args.output.resolve())
