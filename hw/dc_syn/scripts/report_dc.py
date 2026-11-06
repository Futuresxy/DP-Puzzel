#!/usr/bin/env python3
"""Conservative analysis of official DC reports; missing evidence stays UNKNOWN."""
import csv
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def read(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def project_path(path):
    try:
        return Path(path).relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def timing(qor, detail, hold=False):
    prefix = r"Design \(Hold\)" if hold else "Design"
    total = re.search(prefix + r"\s+WNS:\s*(" + NUMBER + r")\s+TNS:\s*(" + NUMBER +
                      r")\s+Number of Violating Paths:\s*(\d+)", qor)
    paths = [float(v) for v in re.findall(r"slack\s+\([^)]+\)\s+(" + NUMBER + ")", detail)]
    values = [float(v) for v in total.groups()] if total else [None, None, None]
    # DC QoR prints positive WNS/TNS violation magnitudes. Publish signed values.
    if total and values[2] > 0:
        values[0], values[1] = -abs(values[0]), -abs(values[1])
    worst = min(paths) if paths else None
    violated = any(v is not None and v < 0 for v in values[:2]) or (
        values[2] is not None and values[2] > 0) or (worst is not None and worst < 0)
    status = "FAIL" if violated else "PASS" if total and paths else "UNKNOWN"
    return {"status": status, "wns_ns": values[0], "tns_ns": values[1],
            "violating_paths": int(values[2]) if total else None, "worst_reported_slack_ns": worst}


def critical_path(detail):
    result = {}
    for key, pattern in (("startpoint", r"Startpoint:\s*(\S+)"),
                         ("endpoint", r"Endpoint:\s*(\S+)"),
                         ("path_group", r"Path Group:\s*(\S+)")):
        match = re.search(pattern, detail)
        result[key] = match.group(1) if match else None
    for key, pattern in (("arrival_ns", r"data arrival time\s+(" + NUMBER + ")"),
                         ("required_ns", r"data required time\s+(" + NUMBER + ")"),
                         ("slack_ns", r"slack\s+\([^)]+\)\s+(" + NUMBER + ")")):
        match = re.search(pattern, detail)
        result[key] = float(match.group(1)) if match else None
    return result


def vt_usage(text, config):
    if not config:
        return None
    # First lvt row is cell count; default constraint denominator excludes blackboxes.
    row = re.search(r"^lvt\s+\d+\s+\(([\d.]+)%\)\s+\d+\s+\([\d.]+%\)\s+\d+\s+\(([\d.]+)%\)", text, re.M)
    actual = float(row[2]) if row else None
    return dict(max_cell_percent=config["max_lvt_percent"], measured_nonblackbox_cell_percent=actual,
                measured_all_cell_percent=float(row[1]) if row else None,
                status="UNKNOWN" if actual is None else "PASS" if actual <= config["max_lvt_percent"] else "FAIL")


def analyze(run, resolved):
    reports = run / "reports"
    errors = []
    area_text = read(reports / "area.rpt")
    area = {}
    for key, label in (("total_cell_area_um2", "Total cell area"),
                       ("combinational_area_um2", "Combinational area"),
                       ("sequential_area_um2", "Noncombinational area")):
        match = re.search(re.escape(label) + r":\s*(" + NUMBER + ")", area_text)
        area[key] = float(match.group(1)) if match else None
    if any(v is None or not math.isfinite(v) or v < 0 for v in area.values()) or not area["total_cell_area_um2"]:
        errors.append("Missing or invalid official cell area")
    qor = read(reports / "qor.rpt")
    version = re.search(r"Version:\s*(\S+)", qor)
    if not version:
        errors.append("Missing measured DC version")
    libraries = set(re.findall(r"^\s+(\S+)\s+\(File:.*?\.db\)", area_text, re.M))
    if not libraries or not libraries <= set(resolved["technology"]["target_libraries"]):
        errors.append("Mapped library not proven to match selected targets")
    if re.search(r"unmapped components|\bgtech\b", area_text, re.I):
        errors.append("Unmapped/generic logic")
    quality = dict(re.findall(r"^(\w+)\t([^\n]+)$", read(reports / "quality.tsv"), re.M))
    if quality.get("design_check_pass") != "1" or quality.get("unresolved_leaf_count") != "0":
        errors.append("Design check failed or unresolved leaves")
    if quality.get("clock_count") != "1":
        errors.append("v1 requires exactly one timing clock")
    check = read(reports / "check_timing.rpt")
    coverage = ("DP_TIMING_CHECKS_BEGIN" in check and "DP_TIMING_CHECKS_END" in check and
                not re.search(r"warning\s*:|error\s*:|fatal\s*:", check, re.I))
    if not coverage:
        errors.append("Timing checks missing or contain warnings; review unconstrained endpoints")
    for name in ("check_design.rpt", "units.rpt", "area_hierarchy.rpt", "constraints.rpt",
                 "reference.rpt", "cell_usage.tsv"):
        if not read(reports / name).strip():
            errors.append("Missing required report: " + name)
    if resolved["constraints"]["clock_gating"] and not read(reports / "clock_gating.rpt").strip():
        errors.append("Missing clock-gating report")
    logs = read(run / "logs/dc.stdout.log") + "\n" + read(run / "logs/dc.stderr.log")
    fatal = re.findall(r"^\s*(?:Error:|Fatal:|DP_DC_FATAL:).*$", logs, re.M | re.I)
    if fatal:
        errors.append("DC errors: " + fatal[0].strip())
    warnings = re.findall(r"^\s*Warning:.*$", logs, re.M | re.I)
    ignored = [w for w in warnings if re.search(r"ignor|not supported|cannot find|can't find|no .*match|no effect", w, re.I)]
    if ignored:
        errors.append("Ignored/unsupported setting: " + ignored[0].strip())
    if read(run / "exit_code.txt").strip() != "0":
        errors.append("DC process did not exit successfully")
    if read(run / "DC_COMPLETE").strip() != "DP_DC_V1_EXPORTS_COMPLETE":
        errors.append("Missing complete-export marker")
    artifacts = []
    names = [resolved["gate"]["top"] + suffix for suffix in ("_mapped.v", ".sdc", ".ddc")]
    if resolved["constraints"]["write_sdf"]:
        names.append(resolved["gate"]["top"] + ".sdf")
    for name in names:
        path = run / "netlist" / name
        if not path.is_file() or not path.stat().st_size:
            errors.append("Missing export: " + name)
        else:
            artifacts.append("netlist/" + name)
    stage_reports = reports
    stage_meta = run / "stage_analysis.json"
    if stage_meta.is_file():
        meta = json.loads(stage_meta.read_text())
        if meta.get("status") == "passed" and meta.get("source_run") == run.name:
            stage_reports = run / meta["analysis_dir"] / "reports"
    setup = timing(qor, read(reports / "timing_setup.rpt"))
    hold = timing(qor, read(reports / "timing_hold.rpt"), True)
    timing_status = "FAIL" if "FAIL" in (setup["status"], hold["status"]) else (
        "PASS" if coverage and setup["status"] == hold["status"] == "PASS" else "UNKNOWN")
    valid = not errors
    vt = vt_usage(read(reports / "threshold_voltage_group.rpt"), resolved["technology"].get("multi_vt"))
    flow_pass = valid and timing_status == "PASS" and (vt is None or vt["status"] == "PASS")
    return {"schema_version": 2, "run_id": run.name, "purpose": resolved.get("purpose", "RTL 综合面积与时序检查"),
            "time": resolved["created_at"], "top": resolved["gate"]["top"],
            "source_files": [project_path(p) for p in resolved["gate"]["sources"]],
            "rtl_fingerprint": resolved["gate"]["rtl_fingerprint"],
            "export_id": resolved["gate"]["export_id"],
            "status": "measured" if valid else "invalid",
            "synthesis_valid": valid, "timing_pass": valid and timing_status == "PASS", "flow_pass": flow_pass,
            "timing_status": timing_status if valid else "UNKNOWN", "errors": errors, "warnings": warnings,
            "area_source": "dc_standard_cell_synthesis", "area_unit": "um2", "area": area,
            "setup": setup, "hold": hold, "unconstrained_endpoints_status": "checked_clean" if coverage else "unknown",
            "dc_version": version.group(1) if version else None,
            "technology": {k: v for k, v in resolved["technology"].items() if k != "reference_dc_version"},
            "parameters": resolved["gate"].get("parameters", {}),
            "hold_repair": resolved.get("hold_repair"),
            "critical_setup_path": critical_path(read(reports / "timing_setup.rpt")),
            "stage_setup_paths": {p.stem[7:]: critical_path(read(p)) for p in sorted(stage_reports.glob("timing_S*.rpt"))},
            "clock_period_ns": resolved["constraints"]["period_ns"],
            "multi_vt": vt,
            "clock_gating": resolved["constraints"]["clock_gating"],
            "hierarchy": resolved["constraints"]["hierarchy"],
            "frequency_mhz": 1000.0 / resolved["constraints"]["period_ns"],
            "netlist_files": artifacts, "power_ready": False}


def compact_record(summary):
    return {"purpose": summary["purpose"], "time": summary["time"], "technology": summary["technology"],
            "export_id": summary["export_id"], "rtl_fingerprint": summary["rtl_fingerprint"],
            "parameters": summary.get("parameters", {}), "multi_vt": summary.get("multi_vt"),
            "hold_repair": summary.get("hold_repair"),
            "critical_setup_path": summary.get("critical_setup_path"),
            "stage_setup_paths": summary.get("stage_setup_paths", {}),
            "source_files": summary["source_files"], "run": "hw/dc_syn/runs/" + summary["run_id"],
            "dc_version": summary["dc_version"], "frequency_mhz": summary["frequency_mhz"],
            "clock_gating": summary["clock_gating"],
            "result": {"synthesis_valid": summary["synthesis_valid"],
                       "total_area_um2": summary["area"]["total_cell_area_um2"],
                       "combinational_area_um2": summary["area"]["combinational_area_um2"],
                       "sequential_area_um2": summary["area"]["sequential_area_um2"],
                       "setup": summary["setup"]["status"], "hold": summary["hold"]["status"],
                       "flow_pass": summary.get("flow_pass", summary["timing_pass"]),
                       "setup_wns_ns": summary["setup"]["wns_ns"],
                       "setup_tns_ns": summary["setup"]["tns_ns"],
                       "setup_violating_paths": summary["setup"]["violating_paths"],
                       "setup_slack_ns": summary["setup"]["worst_reported_slack_ns"],
                       "hold_slack_ns": summary["hold"]["worst_reported_slack_ns"]}}


def write_summary(run, summary):
    (run / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    row = {"run_id": summary["run_id"], "export_id": summary["export_id"],
           "status": summary["status"], "timing_status": summary["timing_status"],
           "timing_pass": summary["timing_pass"], "dc_version": summary["dc_version"],
           "time": summary["time"], "purpose": summary["purpose"], "process": summary["technology"]["process"]}
    row.update(summary["area"])
    for kind in ("setup", "hold"):
        row.update({kind + "_" + k: v for k, v in summary[kind].items()})
    with (run / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    context = {"run_id": summary["run_id"], "export_id": summary["export_id"], "status": summary["status"],
               "timing": summary["timing_status"], "area": summary["area"]["total_cell_area_um2"],
               "comb_area": summary["area"]["combinational_area_um2"],
               "seq_area": summary["area"]["sequential_area_um2"],
               "errors": "; ".join(summary["errors"]) or "无", "dc": summary["dc_version"],
               "technology": summary["technology"]["process"], "pvt": summary["technology"]["pvt"],
               "time": summary["time"], "purpose": summary["purpose"],
               "sources": ", ".join(summary["source_files"]),
               "clock_gating": summary["clock_gating"], "hierarchy": summary["hierarchy"],
               "period": summary["clock_period_ns"]}
    for kind in ("setup", "hold"):
        context.update({kind + "_" + k: v for k, v in summary[kind].items()})
    context = {k: "unknown" if v is None else v for k, v in context.items()}
    template = read(run / "inputs/report.md.in")
    (run / "REPORT.md").write_text(template.format(**context), encoding="utf-8")
