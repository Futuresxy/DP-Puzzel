"""Publication ternary plots from frozen workload coordinates and exact regions.

Run directly to redraw figures only; reproduce.py also calls the same renderer.
Region percentages describe geometric coverage, not hardware area or probability.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.path import Path as PolygonPath
import numpy as np
from simplex import HEIGHT, xy

ROOT = Path(__file__).resolve().parents[1]
MODEL_STYLES = (("#253c59", "o"), ("#825696", "s"), ("#98652a", "^"))
REGION_COLORS = ("#ede8f2", "#fce6d5", "#dae3f5", "#e3f2d9")
AXIS_COLORS = ("#306e95", "#b67232", "#427f65")
RATIOS = ("1:2:4", "1:2:6", "1:2:8", "1:4:8")
MODELS = ("DeepSeek-V4-Flash", "DeepSeek-V4-Pro", "DeepSeek-V4.1-Flash")
# Same serif preference as data/H16Q32E64_area/plot_area_comparison.py.
SERIF_FONTS = ["Times New Roman", "Liberation Serif", "Nimbus Roman", "DejaVu Serif"]
READING_EXAMPLE = (.2, .3, .5)


def style():
    plt.rcParams.update({
        "font.family": "serif", "font.serif": SERIF_FONTS,
        "font.size": 8, "mathtext.fontset": "stix", "axes.unicode_minus": False,
    })


def draw_axes(ax):
    """Three barycentric scales: H on Q-H, Q on E-Q, E on H-E."""
    for family in range(3):
        other = [i for i in range(3) if i != family]
        for value in np.arange(.2, 1, .2):
            ends = np.zeros((2, 3))
            ends[:, family] = value
            ends[0, other[0]] = 1-value
            ends[1, other[1]] = 1-value
            ax.plot(*xy(ends).T, color="#87919b", lw=.35, alpha=.5, zorder=2)

    for value in np.linspace(0, 1, 6):
        positions = ((value/2, HEIGHT*value), (1-value, 0),
                     (.5+.5*value, HEIGHT*(1-value)))
        normals = ((-HEIGHT, .5), (0, -1), (HEIGHT, .5))
        for position, normal in zip(positions, normals):
            point, direction = np.array(position), np.array(normal)
            ax.plot(*np.array([point, point+.014*direction]).T,
                    color="#333333", lw=.55, zorder=3)
            ax.text(*(point+.045*direction), str(round(value*100)),
                    ha="center", va="center", fontsize=7)

    border = xy([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]])
    ax.plot(*border.T, color="#343d46", lw=.8, zorder=3)
    ax.text(.5, HEIGHT+.09, "H (BF16)", ha="center", va="center", weight="bold", fontsize=8.5)
    ax.text(-.045, -.095, "Q (FP8)", ha="center", va="center", weight="bold", fontsize=8.5)
    ax.text(1.045, -.095, "E (FP4)", ha="center", va="center", weight="bold", fontsize=8.5)
    ax.text(.12, .49, "H FLOP share (%)", rotation=60, ha="center", va="center", fontsize=8)
    ax.text(.5, -.10, "Q FLOP share (%)", ha="center", va="center", fontsize=8)
    ax.text(.96, .43, "E FLOP share (%)", rotation=-60, ha="center", va="center", fontsize=8)


def draw_regions(ax, regions, objective, ratios):
    for region in regions:
        if region["fraction"] <= 1e-10:
            continue
        ax.fill(*xy(region["vertices_hqe"]).T, facecolor=REGION_COLORS[region["index"]],
                edgecolor="#626c76", lw=.65, zorder=1)

    # Keep labels inside their regions and clear of the workload trajectories.
    locations = {
        "time": ((.48, .60), (.713, .345), (.894, .065), (.34, .265)),
        "energy": ((.49, .65), (.711, .395), (.847, .055), (.34, .35)),
    }
    for region in regions:
        if region["fraction"] <= 1e-10:
            continue
        index = region["index"]
        label = f"{ratios[index]}\n{100*region['fraction']:.2f}%"
        vertices = xy(region["vertices_hqe"])
        position = locations[objective][index]
        if not PolygonPath(vertices).contains_point(position):
            position = vertices.mean(axis=0)
        narrow = objective == "energy" and index == 1
        ax.text(*position, label, ha="center", va="center",
                fontsize=6.7 if narrow else 8, weight="bold", linespacing=1.0 if narrow else 1.15,
                zorder=12)


def draw_trajectories(ax, points, nv_points, models):
    for is_nv, source in ((False, points), (True, nv_points)):
        for model_index, model in enumerate(models):
            rows = sorted((row for row in source if row["model"] == model),
                          key=lambda row: int(row["context_tokens"]))
            if not rows:
                continue
            coords = xy([[float(row[f"x_{f}"]) for f in "HQE"] for row in rows])
            color, marker = MODEL_STYLES[model_index]
            ax.plot(*coords.T, color=color, marker=marker, ls="-" if is_nv else (0, (3, 2)),
                    markersize=3.0, mfc="white", mew=.7, lw=.95, zorder=8)
            ax.plot(*coords[-1], marker=marker, color=color, ms=4, mfc=color, mew=.6, zorder=10)
            if len(coords) >= 2:
                start, end = coords[-2:]
                ax.annotate("", xy=start+.8*(end-start), xytext=start+.3*(end-start),
                            arrowprops=dict(arrowstyle="->", color=color, lw=.85,
                                            mutation_scale=7), zorder=9)


def draw_panel(ax, points, regions, objective, nv_points, models, ratios):
    draw_regions(ax, regions, objective, ratios)
    draw_axes(ax)
    draw_trajectories(ax, points, nv_points, models)
    ax.set_aspect("equal")
    ax.set_xlim(-.17, 1.17)
    ax.set_ylim(-.15, 1.005)
    ax.axis("off")


def draw_reading_example(ax):
    """An illustrative point, independent of the DeepSeek observations."""
    border = xy([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]])
    ax.plot(*border.T, color="#626c76", lw=.65)
    h_share, q_share, e_share = READING_EXAMPLE
    point = xy([READING_EXAMPLE])[0]
    ends = ((h_share/2, h_share*HEIGHT), (1-q_share, 0),
            ((1+e_share)/2, (1-e_share)*HEIGHT))
    for end, color in zip(ends, AXIS_COLORS):
        ax.plot(*np.array([point, end]).T, color=color, lw=1.0, ls=(0, (3, 1.5)))
    ax.plot(*point, marker="+", ms=5, mew=1, color="#222222")
    ax.text(.5, HEIGHT+.06, "H", ha="center", fontsize=7.5, weight="bold")
    ax.text(-.04, -.05, "Q", ha="center", fontsize=7.5, weight="bold")
    ax.text(1.04, -.05, "E", ha="center", fontsize=7.5, weight="bold")
    ax.text(ends[0][0]-.08, ends[0][1], f"{100*h_share:.0f}", ha="right", va="center",
            color=AXIS_COLORS[0], fontsize=7)
    ax.text(ends[1][0], -.08, f"{100*q_share:.0f}", ha="center", color=AXIS_COLORS[1], fontsize=7)
    ax.text(ends[2][0]+.09, ends[2][1], f"{100*e_share:.0f}", va="center",
            color=AXIS_COLORS[2], fontsize=7)
    ax.set(xlim=(-.18, 1.15), ylim=(-.16, 1.0), aspect="equal")
    ax.axis("off")


def draw_model_legend(ax, models, compact=False):
    """A model-by-deployment matrix identifies all six trajectories explicitly."""
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    if compact:
        # Transpose the matrix: two deployment rows share three model columns.
        ax.text(0, .91, "DeepSeek", fontsize=8, weight="bold", va="center")
        for i, model in enumerate(models):
            middle = .40+.24*i
            color, marker = MODEL_STYLES[i]
            ax.text(middle, .91, model.removeprefix("DeepSeek-"), ha="center", va="center", fontsize=8)
            for height, linestyle in ((.51, (0, (3, 2))), (.11, "-")):
                ax.plot([middle-.06, middle+.06], [height, height], color=color, lw=1, ls=linestyle)
                ax.plot(middle, height, color=color, marker=marker, ms=4, mfc="white", mew=.8)
        ax.text(0, .51, "W4A8 experts", va="center", fontsize=8)
        ax.text(0, .11, "W4A4 experts", va="center", fontsize=8)
        return
    ax.text(0, .92, "DeepSeek model", fontsize=8, weight="bold")
    ax.text(.53, .92, "W4A8 experts", ha="center", va="center", fontsize=8)
    ax.text(.84, .92, "W4A4 experts", ha="center", va="center", fontsize=8)
    for i, model in enumerate(models):
        color, marker = MODEL_STYLES[i]
        height = .67-.22*i
        ax.text(0, height, model.removeprefix("DeepSeek-"), va="center", fontsize=8)
        for middle, linestyle in ((.53, (0, (3, 2))), (.84, "-")):
            ax.plot([middle-.075, middle+.075], [height, height], color=color, lw=1, ls=linestyle)
            ax.plot(middle, height, color=color, marker=marker, ms=4, mfc="white", mew=.8)


def save(fig, output, stem):
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output/f"{stem}.png", dpi=400, bbox_inches="tight", pad_inches=.025)
    plt.close(fig)


def draw_figure(points, regions, objective, nv_points, models, ratios, output):
    """Standalone panel retained for reuse outside the paper."""
    style()
    fig = plt.figure(figsize=(3.55, 3.6))
    ax = fig.add_axes([.02, .15, .96, .84])
    draw_panel(ax, points, regions, objective, nv_points, models, ratios)
    draw_model_legend(fig.add_axes([.10, .01, .83, .12]), models, compact=True)
    save(fig, output, f"k4_n12_prefill_{objective}")


def draw_comparison(points, regions, nv_points, models, ratios, output):
    """Preserve panel scale while using the upper central gap for the reading key."""
    style()
    fig = plt.figure(figsize=(7.16, 3.35))
    for index, objective in enumerate(("time", "energy")):
        ax = fig.add_axes([.012+.5*index, .115, .476, .84])
        draw_panel(ax, points, regions[objective], objective, nv_points, models, ratios)
        title = "(a) Minimum compute latency" if index == 0 else "(b) Minimum DP compute energy"
        fig.text(.25+.5*index, .99, title, ha="center", va="top", weight="bold", fontsize=9)
    draw_reading_example(fig.add_axes([.432, .59, .136, .26]))
    fig.text(.5, .88, "Reading example (%)", ha="center", fontsize=7.5)
    draw_model_legend(fig.add_axes([.12, .007, .76, .105]), models, compact=True)
    save(fig, output, "k4_n12_prefill_comparison")


def redraw(results, output, models=MODELS, ratios=RATIOS):
    sources = [results/name for name in ("regions.json", "prefill_points.csv", "nvfp4_prefill_points.csv")]
    regions = json.loads(sources[0].read_text())
    with sources[1].open() as handle:
        points = list(csv.DictReader(handle))
    with sources[2].open() as handle:
        nv_points = list(csv.DictReader(handle))
    for objective in ("time", "energy"):
        draw_figure(points, regions[objective], objective, nv_points, models, ratios, output)
    draw_comparison(points, regions, nv_points, models, ratios, output)
    manifest = {
        "scope": "figure-only redraw; integer-core latency and MXFP4-proxy energy",
        "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "plot_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "region_percentages": {obj: {ratios[r["index"]]: r["fraction"]*100 for r in regions[obj]}
                               for obj in ("time", "energy")},
        "reading_example_hqe": list(READING_EXAMPLE),
        "example_is_workload_measurement": False,
        "font_family": font_manager.FontProperties(family=["serif"]).get_name(),
        "layout": {"reading_example": "upper_center", "model_legend": "two_rows_three_models",
                   "region_label_background": False},
        "outputs": [f"k4_n12_prefill_{stem}.png" for stem in ("time", "energy", "comparison")],
    }
    (output/"k4_n12_prefill_plot_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT/"data/results")
    parser.add_argument("--output", type=Path, default=ROOT/"figures")
    args = parser.parse_args()
    redraw(args.results, args.output)
