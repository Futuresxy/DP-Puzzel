"""Compare dp_top, Q32E64 and E64 on a shared baseline area scale."""
import argparse
from pathlib import Path

from plot_area import (
    COLORS, HERE, KEY_FIELDS, LABELS, PAPER, SERIF_FONTS, figure_metadata,
    font_manager, plt, read_index, save_figure, values_for,
)
from matplotlib.ticker import PercentFormatter


TOPS = ('dp_top', 'dp_top_q32e64', 'dp_top_e64')
ROW_LABELS = ('dp_top\nT8H16Q32E64', 'Q32E64', 'E64')


def draw(areas, output, dpi, metadata):
    baseline = sum(areas['dp_top'])
    fig, ax = plt.subplots(figsize=(10, 3.55))
    fig.subplots_adjust(left=.15, right=.98, top=.66, bottom=.18)
    fig.text(.55, .97, 'DP area by function', ha='center', va='top',
             fontsize=17, fontweight='bold')
    fig.text(.55, .875, f'dp_top total area = {baseline:,.3f} µm²',
             ha='center', va='top', fontsize=10.5)

    rows = [2, 1, 0]
    left = [0.0] * len(TOPS)
    handles = []
    height = .58
    for index, (label, color) in enumerate(zip(LABELS, COLORS)):
        widths = [areas[top][index] / baseline for top in TOPS]
        bars = ax.barh(rows, widths, left=left, height=height, color=color,
                       edgecolor='white', linewidth=.7, label=label)
        handles.append(bars[0])
        for row, start, width in zip(rows, left, widths):
            if width == 0:
                continue
            center = start + width / 2
            value = f'{width:.1%}'
            if width < .027:
                ax.annotate(value, (center, row + height / 2), xytext=(0, 6),
                            textcoords='offset points', ha='center', va='bottom',
                            fontsize=8, arrowprops={'arrowstyle': '-', 'linewidth': .5,
                                                    'color': '#555555', 'shrinkA': 1, 'shrinkB': 0})
            else:
                text_color = 'white' if index == 0 else '#191919'
                text_size = 7.4 if width < .035 else 8.5
                ax.text(center, row, value, ha='center', va='center',
                        color=text_color, fontsize=text_size)
        left = [start + width for start, width in zip(left, widths)]

    for row, total in zip(rows, left):
        ax.text(total + .012, row, f'{total:.2%}', ha='left', va='center',
                fontsize=10.5, fontweight='bold')

    ax.set_xlim(0, max(left) + .10)
    ax.set_ylim(-.45, 2.55)
    ax.set_yticks(rows, ROW_LABELS)
    ax.tick_params(axis='y', length=0, pad=10)
    ax.tick_params(axis='x', length=0, pad=6)
    ax.set_xticks([0, .2, .4, .6, .8, 1.0])
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.set_xlabel('Area relative to dp_top total', labelpad=8)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E6E6E6', linewidth=.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.legend(handles, LABELS, loc='upper center', bbox_to_anchor=(.55, .82),
               ncol=4, frameon=False, fontsize=10, handlelength=1.25,
               columnspacing=1.5)
    output.parent.mkdir(parents=True, exist_ok=True)
    save_figure(fig, output, dpi, metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--area-data', type=Path, default=HERE / 'area.csv')
    parser.add_argument('--output', type=Path,
                        default=PAPER / 'figures/v19_six/v19_dp_area_comparison.png')
    parser.add_argument('--dpi', type=int, default=600)
    args = parser.parse_args()
    if args.dpi <= 0:
        parser.error('--dpi must be positive')

    table = read_index(args.area_data, KEY_FIELDS)
    areas = {top: values_for([table[top, label] for label in LABELS], 'area_um2')
             for top in TOPS}
    plt.rcParams.update({'font.family': 'serif', 'font.serif': SERIF_FONTS, 'font.size': 11})
    font = font_manager.FontProperties(family=['serif']).get_name()
    metadata = figure_metadata(args.area_data, font)
    metadata['Description'] += ' All segments are normalized to the sum of dp_top areas.'
    draw(areas, args.output, args.dpi, metadata)
    print(args.output)


if __name__ == '__main__':
    main()
