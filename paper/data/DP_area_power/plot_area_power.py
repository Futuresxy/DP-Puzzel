"""Plot only the eight selected DP configurations from editable local CSVs."""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/petile8-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator
import numpy as np

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
FORMATS = ("fp16", "mxfp8_e4m3", "mxfp4_e2m1")
LABELS = ("FP16", "MXFP8 E4M3", "MXFP4 E2M1")
SELECTED = ("1:0:0", "0:0:4", "0:2:0", "0:2:4",
            "1:2:4", "1:2:6", "1:2:8", "1:4:8")
BASELINE = "1:2:4"
PLOT_FORMATS = ("fp16", "mxfp8_e4m3", "mxfp4_e2m1")
STATIC_COLOR = "#CBB6DF"


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))

def write_csv(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def save_figure(fig, output, stem, dpi):
    fig.savefig(output / f"{stem}.png", dpi=dpi,
                bbox_inches="tight", pad_inches=.04, facecolor="white")
    plt.close(fig)

def draw(rows, output, results, dpi):
    groups = [[r for r in rows if r["ratio"] == ratio and int(r["supported"])
               and r["format"] in PLOT_FORMATS] for ratio in SELECTED]
    if [len(g) for g in groups] != [1, 1, 1, 2, 3, 3, 3, 3]:
        raise ValueError("Missing or extra supported precision measurements")
    for group in groups:
        if len({r["format"] for r in group}) != len(group):
            raise ValueError("Duplicate plotted precision")
        if len({r["area_um2"] for r in group}) != 1:
            raise ValueError("Physical area cannot vary with runtime precision")
        for r in group:
            if not math.isclose(float(r["dynamic_mw"]) + float(r["static_mw"]),
                                float(r["total_mw"]), abs_tol=1e-10):
                raise ValueError("Total power does not reconcile")
    plotted = [dict(r) for group in groups for r in group]
    reference = next(Decimal(r["total_mw"]) for r in plotted
                     if r["ratio"] == BASELINE and r["format"] == "fp16")
    if reference <= 0:
        raise ValueError("Power reference must be positive")
    for r in plotted:
        r.update(power_reference_ratio=BASELINE, power_reference_format="fp16",
                 power_reference_total_mw=str(reference))
        for name in ("dynamic", "static", "total"):
            r[name + "_over_reference"] = str(Decimal(r[name + "_mw"]) / reference)
    area_rows = [{k: group[0][k] for k in ("ratio", "H", "Q", "E", "frequency_mhz",
                 "process", "area_um2", "area_over_F")} for group in groups]
    for row in area_rows:
        row["area_1e3_um2"] = str(Decimal(row["area_um2"]) / Decimal(1000))
    write_csv(results / "selected8_power.csv", plotted)
    write_csv(results / "selected8_area.csv", area_rows)
    plt.rcParams.update({"font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
        "font.size": 10, "axes.labelsize": 11, "ytick.labelsize": 9,
        "axes.edgecolor": "#5D6770", "text.color": "#263340",
        "axes.labelcolor": "#263340", "xtick.color": "#263340",
        "ytick.color": "#263340"})

    # AREA: measured 22 nm area, in thousands of square micrometres.
    centers = np.arange(8)
    values = [float(r["area_1e3_um2"]) for r in area_rows]
    colors = ["#8EADC6", "#F3C58F", "#A1C7C1", "#A3C58E"] + ["#DFA0A6"]*4
    fig, ax = plt.subplots(figsize=(6.8, 2.4))
    fig.subplots_adjust(left=.13, right=.99, bottom=.24, top=.97)
    bars = ax.bar(centers, values, width=.42, color=colors,
                  edgecolor=["#F39A24" if ratio == BASELINE else "#7A7A7A"
                             for ratio in SELECTED],
                  linewidth=[1.8 if ratio == BASELINE else .45 for ratio in SELECTED],
                  zorder=2)
    ax.bar_label(bars, labels=[f"{value:.2f}" for value in values], padding=3, fontsize=7.5)
    for x, area, row in zip(centers, values, area_rows):
        bracket_x = x + .35
        ax.plot([bracket_x, bracket_x], [0, area], color="#777777", linewidth=.65, zorder=3)
        ax.hlines([0, area], bracket_x-.065, bracket_x+.065,
                  color="#777777", linewidth=.65, zorder=3)
        ax.annotate(f"{float(row['area_over_F']):.2f}×", (bracket_x, area/2),
                    xytext=(2.5, 0), textcoords="offset points", ha="left", va="center",
                    rotation=90, fontsize=7, color="#333333", zorder=4)
    ax.set_xlim(-.5, 7.85)
    ax.set_ylim(0, max(values)*1.13)
    ax.set_xticks(centers, SELECTED)
    ax.tick_params(axis="x", length=0, pad=5, labelsize=8)
    ax.set_xlabel("Throughput ratio", labelpad=6)
    ax.set_ylabel("DotProduct Area (10³ µm²)", fontsize=10)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E3E7EB", linewidth=.55)
    for x in np.arange(.5, 7, 1):
        ax.axvline(x, color="#DDDDDD", linestyle="--", linewidth=.4, zorder=0)
    save_figure(fig, output, "selected8_area", dpi)

    # POWER: absolute mW bars and full-height relative-power brackets.
    widths = np.array([len(g) + .9 for g in groups])
    edges = np.r_[0, np.cumsum(widths)]
    centers = (edges[:-1] + edges[1:])/2
    power_colors = {"fp16": "#8EADC6", "mxfp8_e4m3": "#A1C7C1", "mxfp4_e2m1": "#F3C58F"}
    fig, ax = plt.subplots(figsize=(8.4, 2.8))
    fig.subplots_adjust(left=.10, right=.99, bottom=.24, top=.86)
    ax.set_xlim(edges[0], edges[-1])
    ax.set_xticks(centers, SELECTED)
    ax.tick_params(axis="x", length=0, pad=5, labelsize=8)
    ax.set_xlabel("Throughput ratio", labelpad=6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E3E7EB", linewidth=.55)
    for edge in edges[1:-1]:
        ax.axvline(edge, color="#DDDDDD", linestyle="--", linewidth=.4, zorder=0)
    index = {(r["ratio"], r["format"]): r for r in plotted}
    for cx, group in zip(centers, groups):
        for j, source in enumerate(group):
            r = index[source["ratio"], source["format"]]
            x = cx + j - (len(group)-1)/2
            static, dynamic, total = (float(r[k + "_mw"]) for k in ("static", "dynamic", "total"))
            ax.bar(x, static, width=.42, color=STATIC_COLOR,
                   edgecolor="#7A7A7A", linewidth=.45, zorder=2)
            ax.bar(x, dynamic, bottom=static, width=.42, color=power_colors[r["format"]],
                   edgecolor="#7A7A7A", linewidth=.45, zorder=2)
            if r["ratio"] == BASELINE and r["format"] == "fp16":
                ax.bar(x, total, width=.42, fill=False, edgecolor="#F39A24", linewidth=1.8, zorder=3)
            ax.annotate(f"{total:.2f}", (x, total), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom", fontsize=7.5)
            bracket_x = x + .35
            ax.plot([bracket_x, bracket_x], [0, total], color="#777777", linewidth=.65, zorder=3)
            ax.hlines([0, total], bracket_x-.065, bracket_x+.065,
                      color="#777777", linewidth=.65, zorder=3)
            ax.annotate(f"{float(r['total_over_reference']):.2f}×", (bracket_x, total/2),
                        xytext=(2.5, 0), textcoords="offset points", ha="left", va="center",
                        rotation=90, fontsize=7, color="#333333", zorder=4)
    maximum = max(float(r["total_mw"]) for r in plotted)
    ax.set_ylim(0, maximum*1.13)
    ax.set_ylabel("DotProduct Power (mW)", fontsize=10)
    ax.yaxis.set_major_locator(MultipleLocator(20))
    handles = [Patch(facecolor=power_colors[fmt], edgecolor="#7A7A7A", linewidth=.45,
                     label=LABELS[FORMATS.index(fmt)]) for fmt in PLOT_FORMATS]
    handles.append(Patch(facecolor=STATIC_COLOR, edgecolor="#7A7A7A", linewidth=.45,
                         label="Static (bottom)"))
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, 1.01),
              ncols=4, frameon=False, fontsize=8, columnspacing=1.5,
              handletextpad=.4, handlelength=1.4)
    save_figure(fig, output, "selected8_power", dpi)
    stats = dict(configurations=8, area_style="pastel bars with area and ratio annotations", area_bars=8,
        area_reference=BASELINE, power_bars=len(plotted), plotted_formats=list(PLOT_FORMATS),
        power_reference_ratio=BASELINE, power_reference_format="fp16",
        power_reference_total_mw=str(reference), power_group_widths=widths.tolist(),
        static_position="bottom", static_color=STATIC_COLOR, precision_capability_rows={"area": 0, "power": 0},
        area_unit="1000 um2", area_process=area_rows[0]["process"],
        area_figure_inches=[6.8, 2.4], area_hatch=False, area_legend=False,
        area_ratio_marker="vertical bracket from zero to bar top",
        area_baseline_edge="#F39A24", area_baseline_linewidth=1.8,
        power_unit="mW", power_figure_inches=[8.4, 2.8],
        power_ratio_marker="vertical bracket from zero to bar top",
        power_colors=power_colors, power_baseline_edge="#F39A24",
        power_highlight_format="fp16", ratio_label_background="none",
        ratio_label_offset_points=[2.5, 0],
        x_tick_labels=list(SELECTED), baseline_annotated=False, output_format="png",
        x_label="Throughput ratio", font_family="Times New Roman",
        y_labels=["DotProduct Area (10³ µm²)", "DotProduct Power (mW)"],
        figures=["selected8_area.png", "selected8_power.png"])
    (results / "plot_manifest.json").write_text(json.dumps(stats, indent=2) + "\n")
    return stats


def positive_decimal(value, field, allow_zero=False):
    number = Decimal(value)
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f'{field} must be finite and {"nonnegative" if allow_zero else "positive"}')
    return number


def load_selected(area_path, power_path):
    areas = read_csv(area_path)
    powers = read_csv(power_path)
    if len(areas) != 8 or {r['ratio'] for r in areas} != set(SELECTED):
        raise ValueError('Area CSV must contain each of the eight selected ratios exactly once')
    area_by_ratio = {r['ratio']:r for r in areas}
    conditions = {(r['process'], Decimal(r['frequency_mhz'])) for r in areas}
    if len(conditions) != 1:
        raise ValueError('All configurations must use the same process and frequency')
    for r in areas:
        positive_decimal(r['area_um2'],r['ratio']+' area')
        positive_decimal(r['frequency_mhz'],r['ratio']+' frequency')
        if tuple(int(r[k]) for k in ('H','Q','E')) != tuple(16*int(x) for x in r['ratio'].split(':')):
            raise ValueError('H/Q/E capacities must equal 16 times the named ratio')
    baseline = positive_decimal(area_by_ratio[BASELINE]['area_um2'],'baseline area')
    index = {}
    for r in powers:
        key = (r['ratio'],r['format'])
        if key in index:
            raise ValueError(f'Duplicate power row: {key}')
        if r['ratio'] not in SELECTED or r['format'] not in PLOT_FORMATS:
            raise ValueError(f'Unexpected power row: {key}')
        index[key] = r
    expected = {(ratio,fmt) for ratio in SELECTED for i,fmt in enumerate(PLOT_FORMATS)
                if int(area_by_ratio[ratio][('H','Q','E')[i]]) > 0}
    if set(index) != expected:
        raise ValueError(f'Power rows must match supported formats; missing={expected-set(index)}, extra={set(index)-expected}')
    result = []
    for ratio in SELECTED:
        a = area_by_ratio[ratio]
        for fmt in PLOT_FORMATS:
            if (ratio,fmt) not in index:continue
            p = index[ratio,fmt]
            dynamic = positive_decimal(p['dynamic_mw'],f'{ratio}/{fmt} dynamic',True)
            static = positive_decimal(p['static_mw'],f'{ratio}/{fmt} static',True)
            result.append(dict(**a,area_over_F=str(Decimal(a['area_um2'])/baseline),format=fmt,
                               supported=1,dynamic_mw=str(dynamic),static_mw=str(static),
                               total_mw=str(dynamic+static),static_basis='measured'))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--area-data',type=Path,default=HERE/'selected8_area.csv')
    parser.add_argument('--power-data',type=Path,default=HERE/'selected8_power.csv')
    parser.add_argument('--output-dir',type=Path,default=PAPER/'figures')
    parser.add_argument('--results-dir',type=Path,default=PAPER/'data/results/selected8')
    parser.add_argument('--dpi',type=int,default=400)
    args=parser.parse_args()
    if args.dpi <= 0:parser.error('--dpi must be positive')
    data=load_selected(args.area_data,args.power_data)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    args.results_dir.mkdir(parents=True,exist_ok=True)
    stats=draw(data,args.output_dir,args.results_dir,args.dpi)
    stats['inputs']=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                     for p in (args.area_data,args.power_data)]
    stats['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (args.results_dir/'plot_manifest.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(f'Selected8: {stats["area_bars"]} area bars, {stats["power_bars"]} power bars; PNGs in {args.output_dir}')


if __name__=='__main__':
    main()
