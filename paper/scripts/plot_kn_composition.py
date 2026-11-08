"""Draw capacity-matched 1:2:8 K/N organizations as a native vector figure.

The illustrative 2x2 base has four Full PEs. K adds E64 inside each PE;
N adds four independent E64 PEs. Both provide H64/Q128/E512 MAC/cycle.
No measurement or analytical result is changed by this schematic.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


OUT = Path(__file__).resolve().parents[1] / "figures"
COLORS = {"K": "#e4dbea", "F": "#f0cccc", "E": "#deecd4"}
plt.rcParams.update({
    "font.family": ["Arial", "DejaVu Sans"],
    "font.size": 7,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def arrow(ax, start, end):
    ax.annotate("", xy=end, xytext=start,
                arrowprops={"arrowstyle": "-|>", "lw": .65,
                            "color": "#555555", "mutation_scale": 5,
                            "shrinkA": 0, "shrinkB": 0})


def array(ax, xs, labels, widths, xbounds):
    rows = [29, 14]
    for y in rows:
        arrow(ax, (xbounds[0] - 3.2, y), (xs[0] - widths[0] / 2, y))
        ax.text(xbounds[0] - 4.3, y, "A", ha="right", va="center", fontsize=6.5)
        for x, label, width in zip(xs, labels, widths):
            color = COLORS["K" if label == "F+E" else label]
            ax.add_patch(Rectangle((x - width / 2, y - 4.4), width, 8.8,
                                   facecolor=color, edgecolor="#222222", lw=.65))
            ax.text(x, y, label, ha="center", va="center", fontsize=7)
        for i in range(len(xs) - 1):
            arrow(ax, (xs[i] + widths[i] / 2, y),
                  (xs[i + 1] - widths[i + 1] / 2, y))
        arrow(ax, (xs[-1] + widths[-1] / 2, y), (xbounds[1] + 1.8, y))
    for x in xs:
        ax.text(x, 39.5, "B", ha="center", va="center", fontsize=6.5)
        arrow(ax, (x, 37.5), (x, 33.4))
        arrow(ax, (x, 24.6), (x, 18.4))
        arrow(ax, (x, 9.6), (x, 4.7))
    ax.add_patch(Rectangle((xbounds[0], 7), xbounds[1] - xbounds[0], 29,
                           facecolor="none", edgecolor="#888888", lw=.55,
                           linestyle=(0, (3, 2))))


def main():
    fig, ax = plt.subplots(figsize=(3.5, 1.65))
    fig.subplots_adjust(left=.01, right=.99, bottom=.01, top=.99)
    ax.set_xlim(-2, 100)
    ax.set_ylim(0, 55)
    ax.axis("off")
    ax.add_patch(Rectangle((3, 49), 3, 2.8, facecolor=COLORS["K"], edgecolor="#222222", lw=.5))
    ax.text(7, 50.4, "F+E: H16Q32E128", va="center", fontsize=6.5)
    ax.add_patch(Rectangle((50, 49), 3, 2.8, facecolor=COLORS["F"], edgecolor="#222222", lw=.5))
    ax.text(54, 50.4, "F: H16Q32E64", va="center", fontsize=6.5)
    ax.add_patch(Rectangle((81, 49), 3, 2.8, facecolor=COLORS["E"], edgecolor="#222222", lw=.5))
    ax.text(85, 50.4, "E: E64", va="center", fontsize=6.5)
    array(ax, [12, 29], ["F+E", "F+E"], [12, 12], [4, 37])
    array(ax, [55, 67, 79, 91], ["F", "F", "E", "E"], [8.2] * 4, [49, 97])
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / "kn_composition.pdf", metadata={"Title": None, "Author": None})
    fig.savefig(OUT / "kn_composition.png", dpi=400)
    plt.close(fig)


if __name__ == "__main__":
    main()
