"""Replot H16Q32E64 area shares from category and total_um2 columns (PNG only)."""
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=HERE/'area_data.csv')
    parser.add_argument('--output',type=Path,default=PAPER/'figures/H16Q32E64_area_pie.png')
    parser.add_argument('--results-dir',type=Path,default=PAPER/'data/results/H16Q32E64_area')
    parser.add_argument('--dpi',type=int,default=600)
    args=parser.parse_args()
    if args.output.suffix.lower()!='.png':parser.error('--output must end in .png')
    if args.dpi<=0:parser.error('--dpi must be positive')
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
