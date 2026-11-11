"""Draw a conceptual PE array and floating-point dot-product flow as vectors."""
from pathlib import Path
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/dac-background-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

OUT=Path(__file__).resolve().parents[1]/'figures'
INK='#292929'; BLUE='#dae3f5'; GREEN='#e3f2d9'; PEACH='#fce6d5'; PURPLE='#ede8f2'


def main():
    plt.rcParams.update({'font.family':'Arial','font.size':7.5,'mathtext.fontset':'stix'})
    fig,ax=plt.subplots(figsize=(3.50,1.80))
    ax.set(xlim=(0,10),ylim=(0,4.85));ax.axis('off')
    def label(x,y,s,**kw):
        return ax.text(x,y,s,ha='center',va='center',color=INK,**kw)
    def box(x,y,w,h,s,fill=BLUE,fs=7.5):
        ax.add_patch(Rectangle((x,y),w,h,facecolor=fill,edgecolor=INK,lw=.65))
        label(x+w/2,y+h/2,s,fontsize=fs)
    def arrow(a,b,**kw):
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=5.5,
                                    color=INK,lw=.65,shrinkA=0,shrinkB=0,**kw))
    # Illustrative m-by-n output-stationary PE array, with row/column reuse.
    x0,y0,step=.96,2.05,.73
    for i in range(3):
        for j in range(3):
            x=x0+j*step;y=y0+(2-i)*step
            box(x,y,.57,.51,'PE',fill=GREEN if (i,j)==(1,1) else BLUE,fs=7)
            if j<2:arrow((x+.57,y+.255),(x+step,y+.255))
            if i<2:arrow((x+.285,y),(x+.285,y-.22))
    for i in range(3):
        y=y0+(2-i)*step+.255
        arrow((.61,y),(x0,y))
        label(.32,y,rf'$\mathbf{{a}}_{i}$',fontsize=8)
    for j in range(3):
        x=x0+j*step+.285
        arrow((x,4.22),(x,4.02))
        label(x,4.51,rf'$\mathbf{{b}}_{j}$',fontsize=8)
    label(2.05,1.72,r'$m\times n$ PEs',fontsize=8)
    # Magnified generic point-product PE; no format-specific implementation.
    arrow((3.25,3.02),(4.57,3.02),linestyle='--')
    label(4.00,3.34,'one PE',fontsize=7)
    box(5.37,2.48,2.31,1.15,'$k$ products\n+ reduction',fill=GREEN,fs=8)
    label(4.81,3.42,r'$\mathbf{a}_{i}$',fontsize=9)
    label(4.81,2.72,r'$\mathbf{b}_{j}$',fontsize=9)
    arrow((5.02,3.42),(5.37,3.42));arrow((5.02,2.72),(5.37,2.72))
    box(8.12,2.73,.55,.55,'+',fill=PEACH,fs=10)
    arrow((7.68,3.005),(8.12,3.005))
    arrow((8.395,3.88),(8.395,3.28));label(8.395,4.16,r'$c_{ij}$',fontsize=9)
    arrow((8.67,3.005),(9.19,3.005));label(9.53,3.005,r'$d_{ij}$',fontsize=9)
    label(7.07,1.83,r'$k=1$: MAC   $k>1$: dot product',fontsize=7.5)
    # Generic processing stages; scale/merge includes inter-group accumulation.
    stages=[('Decode',BLUE),('Exp. add /\nMant. mul',PEACH),
            ('Align /\nreduce',PURPLE),('Scale /\nmerge with $c$',GREEN),
            ('Normalize /\nround',BLUE)]
    for i,(text,fill) in enumerate(stages):
        x=.12+i*2.02
        box(x,.10,1.77,.91,text,fill=fill,fs=7)
        if i<4:arrow((x+1.77,.555),(x+2.02,.555))
    fig.subplots_adjust(left=.01,right=.99,bottom=.02,top=.99)
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT/'tensor_dp_background.png',dpi=400,bbox_inches='tight',pad_inches=.01)
    plt.close(fig)


if __name__=='__main__':
    main()
