"""Import the legacy N12 measurements behind the F and expansion bars."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
RATIOS = (
    "1:2:4", "1:2:6", "1:2:8", "1:2:12", "1:2:16",
    "1:4:4", "1:4:8", "1:4:12", "1:4:16",
    "1:6:4", "1:6:8", "1:6:12", "1:6:16",
    "1:8:4", "1:8:8", "1:8:12", "1:8:16",
)
IMAGE_AREAS = (13.2, 16.3, 18.3, 23.3, 28.5, 20.4, 22.4, 27.1, 32.1,
               27.3, 29.2, 31.2, 35.9, 33.6, 35.6, 37.5, 39.7)
IMAGE = Path("DAC2027/figures/petile21_dc_area_formats.png")
IMAGE_SHA = "f23f2bc5687ed2917a135db8391a6731f7e876fcd8b665cc19be03ea53bcab0d"
DC_ROOT = Path("HW/dc_syn/syn_report")
POWER_ROOT = Path("HW/power_analysis/reports")
MAIN_BATCH = "PETile20_Precision_0928174706"
HALF_BATCH = "PETileFP4Half_N12PPA_1018181343"
FORMATS = ("bf16", "mxfp8_e4m3", "mxfp4_e2m1")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def import_measurements(source, output):
    files = {}

    def read(path):
        full_path = source / path
        files[str(path)] = sha(full_path)
        return full_path.read_text()

    if sha(source / IMAGE) != IMAGE_SHA:
        raise ValueError("The source figure differs from the supplied comparison")
    files[str(IMAGE)] = IMAGE_SHA
    area_catalog = DC_ROOT / MAIN_BATCH / "analysis/area_comparison.csv"
    areas = {row["case"]: row for row in csv.DictReader(read(area_catalog).splitlines())}
    density_file = DC_ROOT / MAIN_BATCH / "analysis/compute_density.csv"
    densities = list(csv.DictReader(read(density_file).splitlines()))
    power = {}
    for batch in (MAIN_BATCH, HALF_BATCH):
        summary = POWER_ROOT / batch / "summary.json"
        for row in json.loads(read(summary)):
            power[batch, row["ratio"], row["format"]] = row

    area_rows, power_rows = [], []
    for ratio, shown_area in zip(RATIOS, IMAGE_AREAS):
        h, q, e = (int(value) for value in ratio.split(":"))
        hqe = f"H{h}Q{q}E{e}"
        batch = HALF_BATCH if ratio == "1:2:6" else MAIN_BATCH
        if batch == HALF_BATCH:
            case = "petile_full16_fp48"
        else:
            density = next(row for row in densities if row["hqe"] == hqe)
            case = density["case"]
            if areas[case]["validity"] != "VALID" or density["timing_status"] != "MET/MET":
                raise ValueError(f"DC acceptance failed for {ratio}")
        dc_run = DC_ROOT / batch / case
        report = dc_run / "report/area_detailed.rpt"
        contents = read(report)
        area = float(re.search(r"^Total cell area:\s+([\d.]+)", contents, re.M)[1])
        dc_version = re.search(r"^Version:\s+(\S+)", contents, re.M)[1]
        if "tcbn12ffcll" not in contents or round(area / 1000, 1) != shown_area:
            raise ValueError(f"Library or figure area mismatch for {ratio}")
        if batch == MAIN_BATCH and area != float(areas[case]["total_cell_area_um2"]):
            raise ValueError(f"DC report and area catalog disagree for {ratio}")
        area_rows.append(dict(
            ratio=ratio, case=case, process="N12", corner="TT", voltage_v=.7, temperature_c=85,
            frequency_mhz=1410, h_mac_per_cycle=16*h, q_mac_per_cycle=16*q, e_mac_per_cycle=16*e,
            area_um2=f"{area:.6f}", image_area_1e3_um2=shown_area, dc_version=dc_version,
            dc_batch=batch, dc_report=str(report), dc_report_sha256=files[str(report)],
        ))
        for fmt, capacity in zip(FORMATS, (16*h, 16*q, 16*e)):
            row = power[batch, hqe, fmt]
            if (row["area_um2"] != area or row["case"] != case or row["mac_per_cycle"] != capacity
                    or Path(row["synthesis_dir"]).parts[-len(dc_run.parts):] != dc_run.parts
                    or row["coverage"] != 1 or row["setup_status"] != "MET" or row["hold_status"] != "MET"):
                raise ValueError(f"Power evidence does not match the DC result for {ratio}/{fmt}")
            power_rows.append(dict(
                ratio=ratio, case=case, format=fmt, mac_per_cycle=capacity, area_um2=f"{area:.6f}",
                frequency_mhz=row["frequency_mhz"], internal_mw=1000*row["internal_w"],
                switching_mw=1000*row["switching_w"], dynamic_mw=1000*(row["internal_w"]+row["switching_w"]),
                static_mw=1000*row["leakage_w"], total_mw=1000*row["total_w"],
                dataset=row["dataset"], measured_cycles=row["cycles"], warmup_cycles=row["warmup_cycles"],
                duration_ns=row["duration_ns"], activity_coverage=row["coverage"],
                activity_audit_status=row["activity_audit_status"], dc_batch=batch,
                power_summary=str(POWER_ROOT / batch / "summary.json"),
            ))
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "petile17_area.csv", area_rows)
    write_csv(output / "petile17_power.csv", power_rows)
    sources = dict(
        upstream_repository="Quant_LLM_Chip_Codesign",
        area_rows=len(area_rows), power_rows=len(power_rows), process="N12",
        scope="Legacy PETile standard-cell area and archived zero-delay VCD/OpenSTA power",
        inputs_sha256=files,
        outputs_sha256={name: sha(output / name) for name in ("petile17_area.csv", "petile17_power.csv")},
    )
    (output / "petile17_sources.json").write_text(json.dumps(sources, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Quant_LLM_Chip_Codesign checkout")
    parser.add_argument("--output", type=Path, default=ROOT / "data/evidence/n12_legacy")
    args = parser.parse_args()
    import_measurements(args.source, args.output)
