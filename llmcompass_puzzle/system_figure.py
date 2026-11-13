"""Controlled ratio / migration heatmaps; analytical MoE latency, not TTFT."""
import argparse
from pathlib import Path

from ratio_dse.common import ROOT, digest, require
from .characterize import write_json
from .summarize_system import read_rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary',type=Path,required=True)
    parser.add_argument('--pdf',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    rows=read_rows(args.summary/'primary_cells.csv')
    ratios=['1:2:4','1:2:6','1:2:8','1:4:4','1:4:8','1:2:12','1:2:16','1:6:12','1:8:16']
    plans=['w4a8','routed_mxfp4','routed_nvfp4']
    values=[float(r['seconds'])*1000 for r in rows if r['seconds']]
    style=ROOT/'.skill/academic-figures/assets/paper.mplstyle'
    with plt.style.context(str(style)):
        fig,axes=plt.subplots(2,2,figsize=(7.15,3.5),layout='constrained',sharex=True,sharey=True)
        cmap=plt.get_cmap('viridis_r').copy();cmap.set_bad('#dddddd')
        for i,cap in enumerate(['','250']):
            for j,regime in enumerate(['fixed','optimized']):
                ax=axes[i,j]
                data=np.full((3,9),np.nan)
                for y,plan in enumerate(plans):
                    for x,ratio in enumerate(ratios):
                        matched=[r for r in rows if (r['plan'],r['ratio'],r['regime'],r['cap_w'])==(plan,ratio,regime,cap)]
                        require(len(matched)==1,'non-unique heatmap cell')
                        r=matched[0]
                        if r['seconds']:data[y,x]=float(r['seconds'])*1000
                im=ax.pcolormesh(np.arange(10)-.5,np.arange(4)-.5,np.ma.masked_invalid(data),
                                 vmin=min(values),vmax=max(values),cmap=cmap,rasterized=False)
                ax.set_ylim(2.5,-.5)
                for y in range(3):
                    for x in range(9):
                        v=data[y,x]
                        ax.text(x,y,'×' if np.isnan(v) else f'{v:.2f}',ha='center',va='center',fontsize=7,
                                color='white' if not np.isnan(v) and v>(min(values)+max(values))/2 else 'black')
                ax.set_xticks(range(9),ratios,rotation=45,ha='right')
                ax.set_yticks(range(3),['W4A8','MXFP4 W4A4','NVFP4 W4A4'])
                title=('Fixed resources' if regime=='fixed' else 'Optimized resources')
                ax.set_title(f'({"abcd"[2*i+j]}) {title}; '+('no cap' if not cap else '250 W scenario'))
                if i==1:ax.set_xlabel('Tensor ratio H:Q:E')
                ax.tick_params(length=0)
        colorbar=fig.colorbar(im,ax=axes.ravel().tolist(),shrink=.9,pad=.02,label='MoE sublayer latency (ms)')
        colorbar.solids.set_rasterized(False)
        args.pdf.parent.mkdir(parents=True,exist_ok=True)
        fig.savefig(args.pdf,metadata={'CreationDate':None,'ModDate':None})
        plt.close(fig)
    write_json(args.evidence,{'input_sha256':digest(args.summary/'primary_cells.csv'),
        'script_sha256':digest(Path(__file__)),'style_sha256':digest(style),
        'pdf_sha256':digest(args.pdf),'matplotlib_version':matplotlib.__version__,
        'scope':'one MoE sublayer; uncalibrated power/quantization assumptions; quality unknown',
        'min_ms':min(values),'max_ms':max(values),'missing':'area/capacity/power/mapping infeasible; see primary_cells.csv'})


if __name__=='__main__':main()
