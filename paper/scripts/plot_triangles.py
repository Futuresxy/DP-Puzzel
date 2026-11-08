"""Compact publication figures; captions belong to LaTeX."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as PolygonPath
from simplex import xy
MODEL_STYLES=(("#26354a","o","-"),("#7e649e","s","--"),("#996b39","^","-."))
REGION_COLORS=("#ede8f2","#fce6d5","#dae3f5","#e3f2d9")
def draw_figure(points, regions, objective, nv_points, models, ratios, output):
    """One compact panel; captions and shared model legend live in LaTeX."""
    plt.rcParams.update({'font.family':'Arial', 'font.size':7.5,
                         'mathtext.fontset':'stix',
                         'hatch.linewidth':.3})
    fig, ax = plt.subplots(figsize=(1.70, 1.57))
    if objective == 'energy':
        v=xy([[1,0,0],[0,1,0],[0,0,1]])
        ax.fill(v[:,0],v[:,1],facecolor='#fafafa',edgecolor='#969696',
                hatch='////',lw=.3,zorder=0)
    for region in regions:
        if region['fraction'] <= 1e-10:
            continue
        v=xy(region['vertices_hqe']);j=region['index']
        ax.fill(v[:,0],v[:,1],facecolor=REGION_COLORS[j],edgecolor='#6d717b',
                lw=.55,zorder=1)
    # Sparse grid and a dark outer edge follow the attached diagram's style.
    for family in range(3):
        other=[i for i in range(3) if i!=family]
        for value in (.25,.5,.75):
            ends=np.zeros((2,3));ends[:,family]=value
            ends[0,other[0]]=1-value;ends[1,other[1]]=1-value
            v=xy(ends)
            ax.plot(v[:,0],v[:,1],color='white',lw=.45,alpha=.8,zorder=2)
    v=xy([[1,0,0],[0,1,0],[0,0,1],[1,0,0]])
    ax.plot(v[:,0],v[:,1],color='#222222',lw=.75,zorder=3)
    ax.text(.5,.90,'H',ha='center',va='bottom',weight='bold',fontsize=8)
    ax.text(0,-.035,'Q',ha='center',va='top',weight='bold',fontsize=8)
    ax.text(1,-.035,'E',ha='center',va='top',weight='bold',fontsize=8)
    positions=({0:(.50,.61),2:(.83,.07),3:(.29,.31)} if objective=='time'
               else {0:(.50,.695),2:(.75,.27),3:(.35,.40)})
    for region in regions:
        if region['fraction']>1e-10:
            j=region['index']
            polygon=xy(region['vertices_hqe'])
            position=positions.get(j,polygon.mean(axis=0))
            if not PolygonPath(polygon).contains_point(position):
                position=polygon.mean(axis=0)
            ax.text(*position,ratios[j],ha='center',va='center',
                    fontsize=7.5,weight='bold',color='#222222',zorder=5)
    for is_nv, source in ((False,points),(True,nv_points)):
        for mi,model in enumerate(models):
            rows=[p for p in source if p['model']==model]
            coords=xy([[r['x_H'],r['x_Q'],r['x_E']] for r in rows])
            color,marker,_=MODEL_STYLES[mi]
            ax.plot(coords[:,0],coords[:,1],color=color,marker=marker,ls='-' if is_nv else '--',
                    markersize=2.4,mfc='white',mew=.6,lw=.85 if is_nv else .6,
                    alpha=1 if is_nv else .75,zorder=8 if is_nv else 6)
            ax.plot(*coords[-1],marker=marker,color=color,ms=3.1,mfc=color,mew=.6,zorder=10)
            if len(coords) < 2:
                continue
            start,end=coords[-2:]
            ax.annotate('',xy=start+.82*(end-start),xytext=start+.22*(end-start),
                        arrowprops=dict(arrowstyle='->',color=color,lw=.7,mutation_scale=5),zorder=9)
    ax.set_aspect('equal');ax.set_xlim(-.055,1.055);ax.set_ylim(-.095,.975);ax.axis('off')
    fig.subplots_adjust(left=.025,right=.975,bottom=.025,top=.975)
    fig.savefig(output/f'k4_n12_prefill_{objective}.png',dpi=400,bbox_inches='tight',pad_inches=.01)
    plt.close(fig)
