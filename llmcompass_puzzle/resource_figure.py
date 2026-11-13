"""Plot area-constrained system resource tradeoffs, not inference speedups."""

import argparse
import csv
from pathlib import Path

from ratio_dse.common import ROOT, digest, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import json
    path = args.run / "area_fitted_resources.csv"
    with path.open() as stream:
        rows = [r for r in csv.DictReader(stream) if r["ratio"] == "1:2:4"]
    rows.sort(key=lambda r: float(r["vector_scale"]))
    require([float(r["vector_scale"]) for r in rows] == [0.5, 1, 2], "expected three vector bundles")
    baseline = rows[1]
    matrix = [float(r["fitted_bf16_tflops"]) / float(baseline["fitted_bf16_tflops"]) for r in rows]
    vector = [float(r["fitted_vector_tflops"]) / float(baseline["fitted_vector_tflops"]) for r in rows]
    style = ROOT / ".skill/academic-figures/assets/paper.mplstyle"
    with plt.style.context(str(style)):
        fig, ax = plt.subplots(figsize=(3.45, 2.35))
        ax.bar([x - 0.18 for x in range(3)], matrix, width=0.34, label="Matrix peak",
               color="#36648b", edgecolor="black", linewidth=0.4)
        ax.bar([x + 0.18 for x in range(3)], vector, width=0.34, label="Vector peak",
               color="#dca65d", edgecolor="black", linewidth=0.4, hatch="//")
        ax.axhline(1, color="0.4", linewidth=0.6, linestyle=":")
        ax.set_xticks(range(3), ["0.5", "1", "2"])
        ax.set_xlabel("Per-SM vector throughput scale")
        ax.set_ylabel("Normalized chip peak throughput")
        ax.set_ylim(0, 2.02)
        ax.set_yticks([0, 0.5, 1, 1.5, 2])
        ax.spines[["top", "right"]].set_visible(False)
        for x, r in enumerate(rows):
            ax.text(x, max(matrix[x], vector[x]) + 0.06, f"{r['fitted_enabled_sms']} SMs",
                    ha="center", va="bottom", fontsize=8)
        ax.legend(loc="upper left", ncol=2, fontsize=8, columnspacing=0.8, handlelength=1.2)
        fig.tight_layout(pad=0.5)
        args.pdf.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.pdf, metadata={"CreationDate": None, "ModDate": None})
        plt.close(fig)
    record = {"input": str(path), "input_sha256": digest(path), "script_sha256": digest(Path(__file__)),
              "style_sha256": digest(style), "pdf": str(args.pdf), "pdf_sha256": digest(args.pdf),
              "matplotlib_version": matplotlib.__version__, "ratio": "1:2:4",
              "normalized_to": {"matrix_tflops": baseline["fitted_bf16_tflops"],
                                "vector_tflops": baseline["fitted_vector_tflops"]},
              "matrix_normalized": matrix, "vector_normalized": vector,
              "scope": "area-feasible peak capacities, not inference latency or calibrated power"}
    args.evidence.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
