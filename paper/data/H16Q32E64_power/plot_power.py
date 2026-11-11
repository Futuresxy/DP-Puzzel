"""Plot six DP total-power distributions from the adjacent power.csv."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
# Reuse the area plot's palette, font and ring style without duplicating them.
sys.path.insert(0, str(HERE.with_name('H16Q32E64_area')))
from plot_area import (
    ARCHITECTURES, KEY_FIELDS, LABELS, MODES, PAPER, POWER_COLUMNS,
    SERIF_FONTS, donut, figure_metadata, font_manager, plt, read_index,
    save_figure, supports, values_for,
)


def plot_power(top, power, path, dpi, metadata):
    fig, axes = plt.subplots(1, len(MODES), figsize=(10.8, 3.8))
    for ax, (mode, title) in zip(axes, MODES.items()):
        if mode in power:
            wedges = donut(ax, power[mode], title, 'mW', label_size=12)
        else:
            ax.set_axis_off()
            ax.text(.5, .56, title, transform=ax.transAxes, ha='center', va='center',
                    fontsize=12, fontweight='bold')
            ax.text(.5, .44, 'Unsupported', transform=ax.transAxes, ha='center', va='center',
                    fontsize=12, color='#666666')
    fig.suptitle(f'{ARCHITECTURES[top]} · Total power', fontsize=16, fontweight='bold', y=.97)
    fig.legend(wedges, LABELS, loc='lower center', ncol=4, frameon=False,
               bbox_to_anchor=(.5, .025), handlelength=1.1, columnspacing=1.4)
    fig.subplots_adjust(left=.015, right=.985, bottom=.15, top=.9, wspace=.12)
    save_figure(fig, path, dpi, metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--power-data', type=Path, default=HERE / 'power.csv')
    parser.add_argument('--figure-dir', type=Path, default=PAPER / 'figures/v19_six')
    parser.add_argument('--dpi', type=int, default=600)
    args = parser.parse_args()
    if args.dpi <= 0:
        parser.error('--dpi must be positive')
    table = read_index(args.power_data, KEY_FIELDS)
    keys = {(top, label) for top in ARCHITECTURES for label in LABELS}
    if set(table) != keys:
        raise ValueError('Power table needs one row per architecture and category')
    data = {}
    for top in ARCHITECTURES:
        rows = [table[top, label] for label in LABELS]
        data[top] = {}
        for mode, column in POWER_COLUMNS.items():
            if supports(top, mode):
                data[top][mode] = values_for(rows, column)
            elif any(row[column] for row in rows):
                raise ValueError(f'{top} does not support {mode}; leave {column} blank')
    plt.rcParams.update({'font.family': 'serif', 'font.serif': SERIF_FONTS, 'font.size': 11})
    font = font_manager.FontProperties(family=['serif']).get_name()
    metadata = figure_metadata(args.power_data, font)
    args.figure_dir.mkdir(parents=True, exist_ok=True)
    for top, power in data.items():
        plot_power(top, power, args.figure_dir / f'v19_{top}_power_functions.png', args.dpi, metadata)
    print(f'6 power figures in {args.figure_dir} ({font}, {args.dpi} dpi)')


if __name__ == '__main__':
    main()
