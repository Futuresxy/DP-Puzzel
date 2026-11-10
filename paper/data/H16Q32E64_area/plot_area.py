"""Plot six DP architectures from compact area and total-power tables."""
import argparse
import csv
import hashlib
import math
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/dp-share-matplotlib')
import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
import matplotlib.pyplot as plt


HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ARCHITECTURES = {
    'dp_top': 'T8H16Q32E64',
    'dp_top_t8h16q32e96': 'T8H16Q32E96',
    'dp_top_t8h16q32e128': 'T8H16Q32E128',
    'dp_top_t8h16q64e128_opt': 'T8H16Q64E128',
    'dp_top_e64': 'E64',
    'dp_top_q32e64': 'Q32E64',
}
MODES = {'bf16': 'BF16', 'mxfp8_e4m3': 'MXFP8 E4M3', 'mxfp4_e2m1': 'MXFP4 E2M1'}
CATEGORY_STYLE = {
    'Mantissa & scale multiplication': ('Multiplication', '#1F77B4'),
    'SOP accumulation': ('Addition & accumulation', '#AEC7E8'),
    'Alignment & shift delta': ('Alignment & shifting', '#FF7F0E'),
    'Exponent processing': ('Exponent processing', '#2CA02C'),
    'Data unpacking': ('Data unpacking', '#98DF8A'),
    'LZD, normalization & rounding': ('Norm & round', '#FFBB78'),
    'Others': ('Others', '#AAAAAA'),
}
LABELS, COLORS = zip(*CATEGORY_STYLE.values())
POWER_COLUMNS = {mode: f'{mode}_total_mw' for mode in MODES}
KEY_FIELDS = ('top', 'category')
AREA_FIELDS = (*KEY_FIELDS, 'area_um2')
POWER_FIELDS = (*KEY_FIELDS, *POWER_COLUMNS.values())
SERIF_FONTS = ['Times New Roman', 'Liberation Serif', 'Nimbus Roman', 'DejaVu Serif']


def supports(top, mode):
    if top == 'dp_top_e64':
        return mode == 'mxfp4_e2m1'
    return top != 'dp_top_q32e64' or mode != 'bf16'


def read_index(path, fields):
    with path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    result = {tuple(row[field] for field in fields): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f'{path.name} has duplicate keys for {fields}')
    return result


def write_table(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def refresh_tables(source_dir, area_output, power_output):
    area = read_index(source_dir / 'seven_functions_area.csv', ('top', 'category'))
    power = read_index(source_dir / 'seven_functions_power.csv', ('top', 'format', 'category'))
    area_keys = {(top, category) for top in ARCHITECTURES for category in CATEGORY_STYLE}
    power_keys = {(top, mode, category) for top, category in area_keys
                  for mode in MODES if supports(top, mode)}
    if set(area) != area_keys or set(power) != power_keys:
        raise ValueError('Expected seven categories for all six areas and 15 supported power points')
    area_rows = {}
    power_rows = {}
    for top in ARCHITECTURES:
        for category, (label, _) in CATEGORY_STYLE.items():
            identity = {'top': top, 'category': label}
            area_rows[top, label] = dict(identity, area_um2=area[top, category]['total_um2'])
            power_row = dict(identity)
            for mode, column in POWER_COLUMNS.items():
                power_row[column] = power[top, mode, category]['total_mw'] if supports(top, mode) else ''
            power_rows[top, label] = power_row
    load_data(area_rows, power_rows)
    write_table(area_output, AREA_FIELDS, area_rows.values())
    write_table(power_output, POWER_FIELDS, power_rows.values())


def values_for(rows, column):
    values = [float(row[column]) for row in rows]
    if not all(math.isfinite(value) and value >= 0 for value in values) or sum(values) <= 0:
        raise ValueError(f'{column} requires finite nonnegative values with a positive sum')
    return values


def load_data(area_table, power_table):
    keys = {(top, label) for top in ARCHITECTURES for label in LABELS}
    if set(area_table) != keys or set(power_table) != keys:
        raise ValueError('Each table needs one row per architecture and category')
    result = {}
    for top in ARCHITECTURES:
        area_rows = [area_table[top, label] for label in LABELS]
        power_rows = [power_table[top, label] for label in LABELS]
        power = {}
        for mode, column in POWER_COLUMNS.items():
            if supports(top, mode):
                power[mode] = values_for(power_rows, column)
            elif any(row[column] for row in power_rows):
                raise ValueError(f'{top} does not support {mode}; leave {column} blank')
        result[top] = (values_for(area_rows, 'area_um2'), power)
    return result


def donut(ax, values, label, unit, label_size=14):
    wedges, _, _ = ax.pie(
        values, colors=COLORS, startangle=90, counterclock=False,
        autopct=lambda percentage: f'{percentage:.1f}%' if percentage else '',
        pctdistance=.79, wedgeprops={'width': .43, 'edgecolor': 'white', 'linewidth': .8},
        textprops={'fontsize': 11, 'color': 'black'},
    )
    ax.text(0, .10, label, ha='center', va='center', fontsize=label_size, fontweight='bold')
    ax.text(0, -.10, f'{sum(values):,.3f} {unit}', ha='center', va='center', fontsize=12)
    return wedges


def save_figure(fig, path, dpi, metadata):
    fig.savefig(path, dpi=dpi, bbox_inches='tight', facecolor='white', metadata=metadata)
    plt.close(fig)


def plot_area(top, area, path, dpi, metadata):
    fig, ax = plt.subplots(figsize=(7.6, 4.5))
    wedges = donut(ax, area, ARCHITECTURES[top], 'µm²')
    ax.legend(wedges, LABELS, loc='center left', bbox_to_anchor=(1, .5),
              frameon=False, labelspacing=.9, handlelength=1.1)
    fig.tight_layout(pad=.3)
    save_figure(fig, path, dpi, metadata)


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


def figure_metadata(data_path, font):
    input_hash = hashlib.sha256(data_path.read_bytes()).hexdigest()
    return {'Description': f'{data_path.name} SHA-256 {input_hash}. Font: {font}. '
                           'Values are unadjusted exclusive cell sums.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--area-data', type=Path, default=HERE / 'area.csv')
    parser.add_argument('--power-data', type=Path, default=HERE.with_name('H16Q32E64_power') / 'power.csv')
    parser.add_argument('--figure-dir', type=Path, default=PAPER / 'figures/v19_six')
    parser.add_argument('--refresh-from', type=Path, help='Refresh both tables from an audited functional report directory')
    parser.add_argument('--dpi', type=int, default=600)
    args = parser.parse_args()
    if args.dpi <= 0:
        parser.error('--dpi must be positive')
    if args.area_data.resolve() == args.power_data.resolve():
        parser.error('Area and power require separate CSV files')
    if args.refresh_from is not None:
        refresh_tables(args.refresh_from, args.area_data, args.power_data)
    data = load_data(read_index(args.area_data, KEY_FIELDS), read_index(args.power_data, KEY_FIELDS))

    plt.rcParams.update({'font.family': 'serif', 'font.serif': SERIF_FONTS, 'font.size': 11})
    font = font_manager.FontProperties(family=['serif']).get_name()
    area_metadata = figure_metadata(args.area_data, font)
    power_metadata = figure_metadata(args.power_data, font)
    args.figure_dir.mkdir(parents=True, exist_ok=True)
    for top, (area, power) in data.items():
        plot_area(top, area, args.figure_dir / f'v19_{top}_area_functions.png', args.dpi, area_metadata)
        plot_power(top, power, args.figure_dir / f'v19_{top}_power_functions.png', args.dpi, power_metadata)
    print(f'12 figures in {args.figure_dir} ({font}, {args.dpi} dpi)')


if __name__ == '__main__':
    main()
