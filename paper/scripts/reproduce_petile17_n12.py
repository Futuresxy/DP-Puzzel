"""Compare 17 legacy N12 PETile ratios under the paper's fixed area budget."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from costs import deploy, mapped_work
from import_petile17_n12 import RATIOS, sha, write_csv
from plot_triangles import draw_petile17_latency
from reproduce import names, table
from simplex import winner_regions
import workloads


ROOT = Path(__file__).resolve().parents[1]
AREA_SOURCE = ROOT / "data/evidence/n12_legacy/petile17_area.csv"


def run(config_path, area_path, output):
    config = json.loads(config_path.read_text())
    config.pop("hardware", None)
    with area_path.open(newline="") as stream:
        areas = list(csv.DictReader(stream))
    if tuple(row["ratio"] for row in areas) != RATIOS:
        raise ValueError("Expected the 17 legacy ratios in source order")
    if any(row["process"] != "N12" for row in areas):
        raise ValueError("All area points must be N12")
    dp_count = config["array_m"] * config["array_n"]
    hardware = []
    for row in areas:
        area = float(row["area_um2"])
        frequency = float(row["frequency_mhz"])
        macs = [int(row[f"{fmt}_mac_per_cycle"]) for fmt in "hqe"]
        if min(area, frequency, *macs) <= 0 or not np.isfinite([area, frequency]).all():
            raise ValueError(f"Invalid area or throughput for {row['ratio']}")
        hardware.append(dict(
            ratio=row["ratio"], area=dp_count*area/1e6,
            capacity=dp_count*2*np.array(macs)*frequency/1e6,
        ))
    options = dict(alpha=config["tensor_area_fraction"], growth=config["peripheral_growth"],
                   baseline_cores=config["baseline_cores"])
    integer = deploy(hardware, **options, integer=True)
    continuous = deploy(hardware, **options)
    budget = config["baseline_cores"]*hardware[0]["area"]/config["tensor_area_fraction"]
    if any(d["count"] < 1 for d in integer):
        raise ValueError("The area budget cannot fit every candidate")
    for d in integer:
        if not d["count"]*d["area"] <= budget+1e-10 < (d["count"]+1)*d["area"]:
            raise ValueError(f"Integer deployment violates the budget for {d['ratio']}")

    coefficients = 1/np.array([d["capacity"] for d in integer])
    regions = winner_regions(coefficients)
    continuous_regions = winner_regions(1/np.array([d["capacity"] for d in continuous]))
    np.testing.assert_allclose(sum(r["fraction"] for r in regions), 1, atol=1e-10)
    np.testing.assert_allclose(sum(r["fraction"] for r in continuous_regions), 1, atol=1e-10)
    for r in regions:
        if r["fraction"] > 1e-10:
            costs = np.array(r["vertices_hqe"]) @ coefficients.T
            if np.any(costs[:, r["index"]] > costs.min(axis=1) + 1e-10):
                raise ValueError(f"Invalid winner polygon for {RATIOS[r['index']]}")
    designs = [
        dict(ratio=row["ratio"], area_um2=float(row["area_um2"]), core_area_mm2=d["area"],
             integer_cores=int(d["count"]), continuous_cores=c["count"],
             pool_tflops=d["capacity"].tolist(), remaining_area_mm2=budget-d["count"]*d["area"])
        for row, d, c in zip(areas, integer, continuous)
    ]
    results = output / "data/results/petile17_n12"
    tables = output / "tables"
    results.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    input_paths = [config_path, area_path]
    input_paths.extend(workloads.SOURCE/model/"inference/config.json" for model in config["models"])
    deployment = dict(
        status="analytical_uncalibrated", scope="Fixed-area useful GEMM service time",
        configuration=config, ratios=list(RATIOS),
        time_coefficients=coefficients.tolist(), time_coefficient_unit="s/TFLOP",
        time_regions=regions, time_regions_continuous=continuous_regions,
        area_budget_mm2=budget, designs=designs,
        inputs_sha256={str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p.name): sha(p)
                       for p in input_paths},
        scripts_sha256={str(p.relative_to(ROOT)): sha(p) for p in (
            Path(__file__).resolve(), ROOT/"scripts/costs.py", ROOT/"scripts/simplex.py",
            ROOT/"scripts/workloads.py", ROOT/"scripts/deepseek_v41.py", ROOT/"scripts/plot_triangles.py",
            ROOT/"scripts/reproduce.py", ROOT/"scripts/import_petile17_n12.py",
        )},
    )
    (results/"deployment.json").write_text(json.dumps(deployment, indent=2) + "\n")

    by_profile = {}
    evaluations = []
    for profile in ("reference_work", "nvfp4_experts"):
        points = []
        for model in config["models"]:
            for context in config["contexts"]:
                f, excluded, _ = mapped_work(model, "prefill", context, profile, config["batch"])
                work = np.array([f[0], f[1], f[2]+f[3]])
                total = work.sum()
                times = coefficients @ (work/1e12)
                h, q, e = work/total
                point_id = f"{model}/{profile}/{context}"
                points.append(dict(
                    point_id=point_id, model=model, profile=profile, context_tokens=context,
                    x_H=h, x_Q=q, x_E=e, total_hqe_flops=int(total), excluded_FP32_flops=int(excluded),
                    fastest=names(times, RATIOS), best_time_ms=1000*times.min(),
                    speedup_vs_124=times[0]/times.min(),
                ))
                evaluations.extend(dict(point_id=point_id, ratio=ratio, time_ms=1000*time)
                                   for ratio, time in zip(RATIOS, times))
        by_profile[profile] = points
    reference, nv = by_profile.values()
    write_csv(results/"prefill_points.csv", reference+nv)
    write_csv(results/"prefill_evaluations.csv", evaluations)
    rows = [
        (f"${ratio}$", d["integer_cores"], f'{100*c["fraction"]:.2f}\\%', f'{100*r["fraction"]:.2f}\\%')
        for ratio, d, c, r in zip(RATIOS, designs, continuous_regions, regions)
    ]
    table_path = tables/"petile17_region_table.tex"
    table(table_path, "lrrr", ("Ratio", "Cores", "Time (cont.)", "Time (int.)"), rows)
    table_path.write_text(table_path.read_text().replace("scripts/reproduce.py", "scripts/reproduce_petile17_n12.py", 1))
    draw_petile17_latency(reference, nv, regions, config["models"], RATIOS, output/"figures")
    print(f"{len(RATIOS)} ratios, {len(reference)+len(nv)} workload points, area budget {budget:.3f} mm²")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT/"data/inputs/experiment.json")
    parser.add_argument("--area", type=Path, default=AREA_SOURCE)
    parser.add_argument("--output", type=Path, default=ROOT, help="Output root for figures, tables and data")
    args = parser.parse_args()
    run(args.config.resolve(), args.area.resolve(), args.output.resolve())
