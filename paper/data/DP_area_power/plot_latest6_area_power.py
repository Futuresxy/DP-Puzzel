"""Plot N12 DP area and workload power from the six-DP or combined records."""

import argparse
import csv
import hashlib
import json
import math
import platform
from pathlib import Path

from plot_area_power import (
    PAPER, Patch, MultipleLocator, matplotlib, np, plt,
    read_csv, save_figure,
)

HERE = Path(__file__).resolve().parent
ROOT = PAPER.parent
DC_SOURCE = ROOT / "hw/dc_syn/records/v19_six_dp_20261110.json"
POWER_SOURCE = ROOT / "hw/power/records/v19_six_architectures_20261110.json"
POWER_CSV = POWER_SOURCE.with_suffix(".csv")
# H:Q:E MAC/cycle ratios, divided by the common H16 capacity.
CONFIGS = (
    ("dp_top_e64", "0:0:4", (0, 0, 64)),
    ("dp_top_q32e64", "0:2:4", (0, 32, 64)),
    ("dp_top", "1:2:4", (16, 32, 64)),
    ("dp_top_t8h16q32e96", "1:2:6", (16, 32, 96)),
    ("dp_top_t8h16q32e128", "1:2:8", (16, 32, 128)),
    ("dp_top_t8h16q64e128_opt", "1:4:8", (16, 64, 128)),
)
FORMATS = ("bf16", "mxfp8_e4m3", "mxfp4_e2m1")
COLORS = dict(zip(FORMATS, ("#8EADC6", "#A1C7C1", "#F3C58F")))
LABELS = ("BF16", "MXFP8 E4M3", "MXFP4 E2M1")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def refresh_data():
    """Join DC and power by top, run and frozen export; retain reported totals."""
    dc = json.loads(DC_SOURCE.read_text())
    power = json.loads(POWER_SOURCE.read_text())
    require(power["status"] == "PASS", "Power collection did not pass")
    require(power["dc_catalog_sha256"] == digest(DC_SOURCE), "DC catalog hash mismatch")
    records = {r["top"]: r for r in dc["records"]}
    require(set(records) == {c[0] for c in CONFIGS}, "Expected exactly six DP architectures")
    points = {(p["top"], p["format"]): p for p in power["results"]}
    raw_rows = read_csv(POWER_CSV)
    require(len(points) == len(power["results"]) == len(raw_rows) == 15,
            "Expected exactly 15 unique measured power points")
    area_rows = []
    for top, ratio, capacities in CONFIGS:
        r = records[top]
        require(r["result"]["flow_pass"] and r["clock_gating"], f"Invalid DC result: {top}")
        require(r["frequency_mhz"] == power["condition"]["frequency_hz"] / 1e6,
                f"Frequency mismatch: {top}")
        technology = r["technology"]
        require(technology["technology_id"] == power["condition"]["technology"]["technology_id"],
                f"Technology mismatch: {top}")
        area_rows.append(dict(
            top=top, architecture=r["capacity"].removesuffix(" opt"), ratio=ratio,
            H=capacities[0], Q=capacities[1], E=capacities[2],
            area_um2=r["result"]["total_area_um2"],
            combinational_area_um2=r["result"]["combinational_area_um2"],
            sequential_area_um2=r["result"]["sequential_area_um2"],
            process=technology["process"], frequency_mhz=r["frequency_mhz"],
            corner=technology["pvt"]["corner"], voltage_v=technology["pvt"]["voltage_v"],
            temperature_c=technology["pvt"]["temperature_c"],
            clock_gating=True, latency_cycles=8, initiation_interval_cycles=1,
            dc_run=r["run"], export_id=r["export_id"],
        ))
    power_rows = []
    for row in raw_rows:
        p = points[row["top"], row["format"]]
        r = records[row["top"]]
        require(p["status"] == p["saif_audit"]["status"] == "PASS", "Invalid power audit")
        require(p["dc_run"] == r["run"] and p["export_id"] == r["export_id"],
                "Power and DC refer to different implementations")
        require(p["area_um2"] == r["result"]["total_area_um2"], "Area mismatch")
        for key, value in row.items():
            require(value == p[key] if isinstance(p[key], str) else float(value) == p[key],
                    f"Power CSV/JSON mismatch: {row['top']}/{row['format']}/{key}")
        power_rows.append(dict(row, dc_run=p["dc_run"], export_id=p["export_id"],
                               power_audit=p["audit_path"], power_audit_sha256=p["audit_sha256"],
                               workload_receipt=p["workload_receipt"],
                               workload_receipt_sha256=p["workload_receipt_sha256"],
                               reused=p["reused"]))
    write_csv(HERE / "latest6_area.csv", area_rows)
    write_csv(HERE / "latest6_power.csv", power_rows)
    sources = dict(
        scope="Existing verified N12 measurements; no new synthesis or power run",
        sources=[dict(path=str(p.relative_to(ROOT)), sha256=digest(p))
                 for p in (DC_SOURCE, POWER_SOURCE, POWER_CSV)],
        source_created_utc=power["created_utc"], condition=power["condition"],
        workload="Qwen3-8B layer 0 MLP down_proj; 1024 independent transactions",
        boundary="Post-synthesis zero-delay, pre-CTS/pre-route; no SDF/SPEF",
        implementation="Repaired v1.8 dp_top baseline; v1.9 mixed and Q32E64 designs; original E64 netlist",
        measurement_batch="All 15 points replayed with fresh native SAIF and Power Compiler in the v1.9 comparison batch",
        power_components="Dynamic = internal + switching; static = leakage",
        total_policy="Keep tool-reported total_mw; component sums differ by report rounding",
        area_reference="dp_top", power_reference="dp_top/bf16",
    )
    (HERE / "latest6_sources.json").write_text(json.dumps(sources, indent=2) + "\n")


def load_data():
    areas = read_csv(HERE / "latest6_area.csv")
    powers = read_csv(HERE / "latest6_power.csv")
    require(len(areas) == 6 and {r["top"] for r in areas} == {c[0] for c in CONFIGS},
            "Expected six unique area rows")
    area_index = {r["top"]: r for r in areas}
    point_index = {(r["top"], r["format"]): r for r in powers}
    expected = {(top, fmt) for top, _, caps in CONFIGS
                for fmt, capacity in zip(FORMATS, caps) if capacity}
    require(len(point_index) == len(powers) and set(point_index) == expected,
            "Measured formats must match the 15 supported architecture/format points")
    groups = []
    for top, ratio, capacities in CONFIGS:
        area = area_index[top]
        require(area["ratio"] == ratio and tuple(int(area[k]) for k in ("H", "Q", "E")) == capacities,
                f"Capacity mismatch: {top}")
        group = []
        for fmt, capacity in zip(FORMATS, capacities):
            if not capacity:
                continue
            row = point_index[top, fmt]
            require(int(row["logical_k"]) == capacity, f"K mismatch: {top}/{fmt}")
            require(float(row["area_um2"]) == float(area["area_um2"]), "Power area mismatch")
            for key in ("dc_run", "export_id"):
                require(row[key] == area[key], f"Provenance mismatch: {key}")
            for key in ("area_um2", "internal_mw", "switching_mw", "dynamic_mw", "static_mw", "total_mw"):
                require(math.isfinite(float(row[key])) and float(row[key]) > 0, f"Invalid {key}")
            require(math.isclose(float(row["internal_mw"]) + float(row["switching_mw"]),
                                 float(row["dynamic_mw"]), rel_tol=0, abs_tol=1e-10),
                    "Dynamic power does not reconcile")
            # Source reports round components independently; keep the tool total.
            require(math.isclose(float(row["dynamic_mw"]) + float(row["static_mw"]),
                                 float(row["total_mw"]), rel_tol=0, abs_tol=5e-4),
                    "Total power exceeds source rounding tolerance (0.0005 mW)")
            group.append(row)
        groups.append(group)
    return [area_index[c[0]] for c in CONFIGS], groups


def load_combined_data(path):
    """Read one area and the three measured formats per full DP, in CSV order."""
    points_by_top = {}
    for row in read_csv(path):
        top = row["top"]
        if top in {"dp_top_e64", "dp_top_q32e64"}:
            continue
        points = points_by_top.setdefault(top, {})
        fmt = row["format"]
        require(fmt not in points, f"Duplicate power point: {top}/{fmt}")
        points[fmt] = row

    require("dp_top" in points_by_top, "Missing dp_top reference")
    areas, groups, ratios = [], [], []
    capacity_fields = ("h_native", "q_native", "e_native")
    for top, points in points_by_top.items():
        require(set(points) == set(FORMATS), f"Expected BF16, MXFP8 E4M3 and MXFP4 E2M1 for {top}")
        group = [points[fmt] for fmt in FORMATS]
        area_row = group[0]
        capacities = tuple(int(area_row[field]) for field in capacity_fields)
        area = float(area_row["area_um2"])
        require(math.isfinite(area) and area > 0, f"Invalid area: {top}")
        for row, capacity in zip(group, capacities):
            point = f"{top}/{row['format']}"
            require(row["status"] == "PASS", f"Measurement did not pass: {point}")
            require(all(row[field] == area_row[field] for field in capacity_fields),
                    f"Inconsistent throughput ratio: {point}")
            require(int(row["native_k"]) == capacity > 0, f"Invalid native K: {point}")
            require(float(row["area_um2"]) == area and row["export_id"] == area_row["export_id"],
                    f"Inconsistent area or RTL export: {point}")
            total = float(row["total_mw"])
            require(math.isfinite(total) and total > 0, f"Invalid total power: {point}")
        areas.append(area)
        groups.append(group)
        ratios.append(":".join(f"{capacity / 16:g}" for capacity in capacities))
    return areas, groups, ratios


def bracket(ax, x, height, ratio):
    x += .35
    ax.plot([x, x], [0, height], color="#777777", linewidth=.65, zorder=3)
    ax.hlines([0, height], x-.065, x+.065, color="#777777", linewidth=.65, zorder=3)
    ax.annotate(f"{ratio:.2f}×", (x, height/2), xytext=(2.5, 0),
                textcoords="offset points", ha="left", va="center", rotation=90,
                fontsize=7, color="#333333", zorder=4)


def style_axes(ax, centers, maximum, ylabel, separators, labels=None):
    ax.set_xticks(centers, labels if labels is not None else [c[1] for c in CONFIGS])
    ax.tick_params(axis="x", length=0, pad=5, labelsize=8)
    ax.set_xlabel("Throughput ratio (H:Q:E)", labelpad=6)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_ylim(0, maximum*1.13)
    ax.yaxis.set_major_locator(MultipleLocator(5))
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E3E7EB", linewidth=.55)
    for x in separators:
        ax.axvline(x, color="#DDDDDD", linestyle="--", linewidth=.4, zorder=0)


def draw_power(groups, output, dpi, ratios, stem, figure_width=9.2, *, file_format="png"):
    """Original latest6 style: measured mW and one dp_top/BF16 ratio reference."""
    plt.rcParams.update({"font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
        "font.size": 10, "axes.labelsize": 11, "ytick.labelsize": 9,
        "axes.edgecolor": "#5D6770", "text.color": "#263340",
        "axes.labelcolor": "#263340", "xtick.color": "#263340", "ytick.color": "#263340"})
    power_ref = float(next(r["total_mw"] for g in groups for r in g
                           if r["top"] == "dp_top" and r["format"] == "bf16"))
    widths = np.array([len(group) + .9 for group in groups])
    edges = np.r_[0, np.cumsum(widths)]
    centers = (edges[:-1] + edges[1:])/2
    fig, ax = plt.subplots(figsize=(figure_width, 2.8))
    fig.subplots_adjust(left=.09, right=.99, bottom=.24, top=.86)
    maximum = max(float(r["total_mw"]) for g in groups for r in g)
    for center, group in zip(centers, groups):
        for index, row in enumerate(group):
            x = center + index - (len(group)-1)/2
            total = float(row["total_mw"])
            baseline = row["top"] == "dp_top" and row["format"] == "bf16"
            bars = ax.bar(x, total, width=.42, color=COLORS[row["format"]],
                          edgecolor="#F39A24" if baseline else "#7A7A7A",
                          linewidth=1.8 if baseline else .45, zorder=2)
            ax.bar_label(bars, labels=[f"{total:.3f}"], padding=3, fontsize=7.5)
            bracket(ax, x, total, total/power_ref)
    style_axes(ax, centers, maximum, "Total Power (mW)", edges[1:-1], labels=ratios)
    ax.set_xlim(edges[0], edges[-1])
    handles = [Patch(facecolor=COLORS[fmt], edgecolor="#7A7A7A", linewidth=.45, label=label)
               for fmt, label in zip(FORMATS, LABELS)]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, 1.01), ncols=3,
              frameon=False, fontsize=8, columnspacing=1.5, handletextpad=.4, handlelength=1.4)
    save_figure(fig, output, stem, dpi, file_format=file_format)
    return dict(power_bars=sum(len(g) for g in groups), formats=list(FORMATS),
                power_layout="ratio groups, widths proportional to supported precision count plus gap",
                power_group_bars=[len(g) for g in groups], power_group_widths=widths.tolist(),
                x_tick_labels=ratios, power_quantity="tool-reported total_mw", power_stacked=False,
                power_reference_top="dp_top", power_reference_format="bf16",
                power_reference_total_mw=power_ref)


def draw(areas, groups, output, dpi):
    plt.rcParams.update({"font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
        "font.size": 10, "axes.labelsize": 11, "ytick.labelsize": 9,
        "axes.edgecolor": "#5D6770", "text.color": "#263340",
        "axes.labelcolor": "#263340", "xtick.color": "#263340", "ytick.color": "#263340"})
    area_ref = float(next(r["area_um2"] for r in areas if r["top"] == "dp_top"))
    values = [float(r["area_um2"])/1000 for r in areas]
    centers = np.arange(6)
    fig, ax = plt.subplots(figsize=(6.8, 2.4))
    fig.subplots_adjust(left=.13, right=.99, bottom=.24, top=.97)
    bars = ax.bar(centers, values, width=.42,
                  color=["#F3C58F", "#A3C58E"] + ["#DFA0A6"]*4,
                  edgecolor=["#F39A24" if r["top"] == "dp_top" else "#7A7A7A" for r in areas],
                  linewidth=[1.8 if r["top"] == "dp_top" else .45 for r in areas], zorder=2)
    ax.bar_label(bars, labels=[f"{v:.2f}" for v in values], padding=3, fontsize=7.5)
    for x, value in zip(centers, values):
        bracket(ax, x, value, value*1000/area_ref)
    style_axes(ax, centers, max(values), "DotProduct Area (10³ µm²)", np.arange(.5, 5, 1))
    ax.set_xlim(-.5, 5.85)
    save_figure(fig, output, "latest6_area", dpi)

    power_metadata = draw_power(groups, output, dpi, [c[1] for c in CONFIGS], "latest6_power")
    return dict(area_bars=6, area_reference_top="dp_top", area_reference_um2=area_ref,
                dpi=dpi, figures=["latest6_area.png", "latest6_power.png"], **power_metadata)


def draw_normalized_area(ratios, values, output, dpi, stem, *, file_format="png"):
    centers = np.arange(len(ratios))
    plt.rcParams.update({"font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
        "font.size": 8, "axes.labelsize": 8, "axes.edgecolor": "#5D6770"})

    fig, ax = plt.subplots(figsize=(3.5 * max(1, len(ratios) / 4), 1.45))
    fig.subplots_adjust(left=.14, right=.99, bottom=.29, top=.97)
    bars = ax.bar(centers, values, width=.45, color="#DFA0A6", edgecolor="#7A7A7A", linewidth=.45)
    ax.bar_label(bars, fmt="%.2f", padding=2, fontsize=7)
    ax.set_xticks(centers, ratios)
    ax.set_xlabel("Throughput ratio (H:Q:E)", labelpad=3)
    ax.set_ylabel("Normalized area", labelpad=3)
    ax.set_ylim(0, max(2.12, max(values) * 1.12))
    ax.yaxis.set_major_locator(MultipleLocator(.5))
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E3E7EB", linewidth=.5)
    ax.axhline(1, color="#777777", linestyle="--", linewidth=.6)
    ax.tick_params(axis="x", length=0, pad=3)
    save_figure(fig, output, stem, dpi, file_format=file_format)


def draw_ratios(areas, groups, output, dpi):
    """Four full-DP candidates; all power ratios use dp_top/BF16."""
    selected = [(a, g) for a, g in zip(areas, groups) if int(a["H"]) > 0]
    require(len(selected) == 4, "Expected four H/Q/E ratio candidates")
    area_ref = float(selected[0][0]["area_um2"])
    power_ref = float(next(r["total_mw"] for r in selected[0][1] if r["format"] == "bf16"))
    ratios = [a["ratio"] for a, _ in selected]
    rows = []
    for area, group in selected:
        row = dict(ratio=area["ratio"], area_um2=float(area["area_um2"]),
                   area_ratio=float(area["area_um2"])/area_ref)
        for point in group:
            fmt = point["format"]
            row[fmt + "_total_mw"] = float(point["total_mw"])
            row[fmt + "_power_ratio"] = float(point["total_mw"])/power_ref
        rows.append(row)
    write_csv(HERE / "ratio4_costs.csv", rows)
    draw_normalized_area(ratios, [row["area_ratio"] for row in rows], output, dpi, "ratio4_area")

    power_groups = [g for _, g in selected]
    # Keep the original bar/label/bracket spacing while removing two ratio groups.
    figure_width = 9.2 * sum(len(g)+.9 for g in power_groups) / sum(len(g)+.9 for g in groups)
    power_metadata = draw_power(power_groups, output, dpi, ratios, "ratio4_power", figure_width)
    return dict(area_bars=4, area_reference_um2=area_ref,
                boundary="Same measured inputs as latest6; no new hardware experiments",
                dpi=dpi, figures=["ratio4_area.png", "ratio4_power.png"], **power_metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--refresh-data", action="store_true", help="Re-export the pinned six-DP HW indexes")
    inputs.add_argument("--combined-csv", type=Path,
                        help="Plot full-DP ratios from a combined area and power CSV as PDFs")
    parser.add_argument("--output-dir", type=Path, default=PAPER / "figures")
    parser.add_argument("--dpi", type=int, default=400)
    parser.add_argument("--scope", choices=("six", "ratios"), default="six",
                        help="Use the six-design or four-ratio view of the legacy CSVs")
    args = parser.parse_args()
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.combined_csv:
        areas, groups, ratios = load_combined_data(args.combined_csv)
        area_ref = next(area for area, group in zip(areas, groups) if group[0]["top"] == "dp_top")
        draw_normalized_area(ratios, [area / area_ref for area in areas], args.output_dir,
                             args.dpi, "dp_ratio_area", file_format="pdf")
        # Leave room between the absolute power labels and the neighboring ratio brackets.
        power = draw_power(groups, args.output_dir, args.dpi, ratios, "dp_ratio_power",
                           figure_width=2 * len(groups), file_format="pdf")
        print(f"{len(areas)} area bars, {power['power_bars']} power bars; PDFs in {args.output_dir}")
        return
    if args.refresh_data:
        refresh_data()
    areas, groups = load_data()
    render = draw_ratios if args.scope == "ratios" else draw
    stem = "ratio4" if args.scope == "ratios" else "latest6"
    manifest = render(areas, groups, args.output_dir, args.dpi)
    manifest["runtime"] = dict(python=platform.python_version(), numpy=np.__version__,
                               matplotlib=matplotlib.__version__)
    manifest["inputs"] = [dict(file=p.name, sha256=digest(p)) for p in
                          (HERE / "latest6_area.csv", HERE / "latest6_power.csv", HERE / "latest6_sources.json")]
    manifest["scripts"] = [dict(file=p.name, sha256=digest(p)) for p in
                           (Path(__file__), HERE / "plot_area_power.py")]
    manifest["outputs"] = [dict(file=name, sha256=digest(args.output_dir / name)) for name in manifest["figures"]]
    (args.output_dir / f"{stem}_plot_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{stem}: {manifest['area_bars']} area bars, {manifest['power_bars']} power bars; PNGs in {args.output_dir}")


if __name__ == "__main__":
    main()
