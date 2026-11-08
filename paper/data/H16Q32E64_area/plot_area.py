"""Plot legacy area data, or current dp_top functional area and SAIF power shares."""
import argparse
import csv
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR','/tmp/petile8-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]


def load_areas(path):
    areas=defaultdict(float)
    with path.open(newline='',encoding='utf-8') as source:
        for row in csv.DictReader(source):
            area=float(row['total_um2'])
            if not row['category'].strip() or not math.isfinite(area) or area<0:
                raise ValueError('Each row needs a category and finite nonnegative total_um2')
            areas[row['category']]+=area
    if not areas or sum(areas.values())<=0:
        raise ValueError('Total area must be positive')
    return areas


def draw(areas,output,dpi):
    plt.rcParams.update({'font.family':'serif',
        'font.serif':['Times New Roman','Liberation Serif','DejaVu Serif'],'font.size':11})
    colors=['#1F77B4','#AEC7E8','#FF7F0E','#2CA02C','#98DF8A','#AAAAAA']
    fig,ax=plt.subplots(figsize=(7.6,4.5))
    wedges,_,_=ax.pie(list(areas.values()),colors=colors,startangle=90,counterclock=False,
        autopct='%1.1f%%',pctdistance=.79,
        wedgeprops={'width':.43,'edgecolor':'white','linewidth':.8},
        textprops={'fontsize':11,'color':'black'})
    total_area=sum(areas.values())
    ax.text(0,.10,'H16Q32E64',ha='center',va='center',fontsize=14,fontweight='bold')
    ax.text(0,-.10,f'{total_area:,.3f} µm²',ha='center',va='center',fontsize=12)
    ax.legend(wedges,list(areas),loc='center left',bbox_to_anchor=(1,.5),frameon=False,
              labelspacing=.9,handlelength=1.1)
    ax.set_aspect('equal');fig.tight_layout(pad=.3)
    fig.savefig(output,dpi=dpi,bbox_inches='tight',facecolor='white',format='png')
    plt.close(fig)



CURRENT_COLORS = ['#8CB5D5', '#E7A39A', '#E6CA7C', '#B79BCB',
                  '#9BC69B', '#80C3C0', '#B6B6B6']
CURRENT_MODES = [('bf16', 'BF16'), ('mxfp8_e4m3', 'MXFP8 E4M3'),
                 ('mxfp4_e2m1', 'MXFP4 E2M1')]


def current_donut(ax, values, label, unit, colors):
    total = sum(values)
    if total <= 0 or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Pie values must be finite, nonnegative, and have a positive sum')
    wedges, _, _ = ax.pie(
        values, colors=colors, startangle=90, counterclock=False,
        autopct=lambda percent: f'{percent:.1f}%' if percent >= 2 else '',
        pctdistance=.83, wedgeprops={'width': .42, 'edgecolor': 'white', 'linewidth': .8},
        textprops={'fontsize': 9})
    ax.text(0, .10, label, ha='center', va='center', fontsize=11, fontweight='bold')
    ax.text(0, -.12, f'{total:,.3f} {unit}', ha='center', va='center', fontsize=10)
    ax.set_aspect('equal')
    return wedges


def plot_current(data_dir, figure_dir, results_dir, dpi):
    area_path = data_dir / 'current_dp_top_area.csv'
    power_path = data_dir / 'current_dp_top_power.csv'
    areas = load_areas(area_path)
    categories = list(areas)
    if len(categories) != len(CURRENT_COLORS):
        raise ValueError('Current policy requires exactly seven functional categories')
    plt.rcParams.update({'font.family': 'serif',
        'font.serif': ['Times New Roman', 'Liberation Serif', 'DejaVu Serif'], 'font.size': 11})
    figure_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    wedges = current_donut(ax, list(areas.values()), 'dp_top', 'µm²', CURRENT_COLORS)
    ax.set_title('T8H16Q32E64: functional cell area', pad=14)
    ax.legend(wedges, categories, loc='center left', bbox_to_anchor=(1, .5),
              frameon=False, labelspacing=1.1)
    fig.text(.5, .025, 'N12 TT · 0.7 V · 85 °C · 1 GHz · precision register gating',
             ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .05, 1, 1))
    area_output = figure_dir / 'current_dp_top_area_share.png'
    fig.savefig(area_output, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    with power_path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(CURRENT_MODES) * len(categories):
        raise ValueError('Expected one power row per format and category')
    power = {(r['format'], r['category']): r for r in rows}
    if len(power) != len(rows):
        raise ValueError('Duplicate format/category power rows')
    fig, axes = plt.subplots(3, 3, figsize=(12, 12))
    metrics = [('dynamic_mw', 'Dynamic power'), ('leakage_mw', 'Leakage power'),
               ('total_mw', 'Total power')]
    totals = {}
    for row_index, (mode, title) in enumerate(CURRENT_MODES):
        totals[mode] = {}
        for column, (metric, metric_title) in enumerate(metrics):
            values = [float(power[(mode, category)][metric]) for category in categories]
            ax = axes[row_index, column]
            wedges = current_donut(ax, values, title, 'mW', CURRENT_COLORS)
            totals[mode][metric] = sum(values)
            if row_index == 0:
                ax.set_title(metric_title, fontsize=14, pad=12)
    fig.suptitle('T8H16Q32E64: functional power shares', fontsize=17, y=.985)
    fig.legend(wedges, categories, loc='lower center', ncol=2, frameon=False,
               bbox_to_anchor=(.5, .035), labelspacing=.8, columnspacing=2)
    fig.text(.5, .012, 'N12 TT · 0.7 V · 85 °C · 1 GHz | Qwen3-8B MLP | native gate SAIF, pre-CTS',
             ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .16, 1, .965), h_pad=1)
    power_output = figure_dir / 'current_dp_top_power_share.png'
    fig.savefig(power_output, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    manifest = dict(
        dataset='current dp_top; independent of legacy area_data.csv',
        total_area_um2=sum(areas.values()), power_totals=totals,
        input_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (area_path, power_path)},
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        outputs=[area_output.name, power_output.name], dpi=dpi,
        denominator='exclusive leaf-cell sum; see current_dp_top_reconciliation.csv',
        percentage_labels='Values below 2% omitted from chart labels; all categories retained')
    (results_dir / 'current_dp_top_plot_manifest.json').write_text(
        json.dumps(manifest, indent=2) + '\n')
    print(f'Current dp_top: {sum(areas.values()):.6f} um2; {area_output}; {power_output}')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=HERE/'area_data.csv')
    parser.add_argument('--output',type=Path,default=PAPER/'figures/H16Q32E64_area_pie.png')
    parser.add_argument('--results-dir',type=Path,default=PAPER/'data/results/H16Q32E64_area')
    parser.add_argument('--dpi',type=int,default=600)
    parser.add_argument('--current', action='store_true', help='Plot the current dp_top area and all three power formats')
    parser.add_argument('--current-data-dir', type=Path, default=HERE)
    parser.add_argument('--figure-dir', type=Path, default=PAPER/'figures')
    args=parser.parse_args()
    if args.output.suffix.lower()!='.png':parser.error('--output must end in .png')
    if args.dpi<=0:parser.error('--dpi must be positive')
    if args.current:
        plot_current(args.current_data_dir, args.figure_dir, args.results_dir, args.dpi)
        return
    areas=load_areas(args.data);total=sum(areas.values())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.results_dir.mkdir(parents=True,exist_ok=True)
    draw(areas,args.output,args.dpi)
    with (args.results_dir/'category_areas.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['category','area_um2','fraction','percent'],lineterminator='\n')
        writer.writeheader()
        writer.writerows(dict(category=k,area_um2=v,fraction=v/total,percent=100*v/total) for k,v in areas.items())
    manifest=dict(total_area_um2=total,categories=len(areas),input_file=args.data.name,
        input_sha256=hashlib.sha256(args.data.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        area_column='total_um2',output=args.output.name,output_format='png')
    (args.results_dir/'plot_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'H16Q32E64: {len(areas)} categories, {total:.3f} um2; PNG at {args.output}')


if __name__=='__main__':
    main()
