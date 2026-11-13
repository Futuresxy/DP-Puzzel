"""Exact half-plane intersections on the H/Q/E simplex."""
import numpy as np
HEIGHT=np.sqrt(3)/2
def workload_grid(divisions):
    return np.array([(h/divisions, q/divisions, (divisions-h-q)/divisions)
                     for h in range(divisions+1) for q in range(divisions-h+1)])

def clip_polygon(poly, normal, bound, tolerance=1e-12):
    if not poly:
        return []
    result = []
    for a, b in zip(poly, poly[1:]+poly[:1]):
        da, db = np.dot(normal, a)-bound, np.dot(normal, b)-bound
        ina, inb = da <= tolerance, db <= tolerance
        if ina:
            result.append(a)
        if ina != inb:
            result.append(a + (b-a)*(da/(da-db)))
    return result

def winner_regions(coefficients):
    """Exact regions for linear costs in FLOP fractions; fractions are geometry, not probabilities."""
    coeff = np.asarray(coefficients)
    regions = []
    for i, a in enumerate(coeff):
        poly = [np.array([1., 0.]), np.array([0., 1.]), np.array([0., 0.])]
        for j, b in enumerate(coeff):
            if i == j:
                continue
            d = a-b
            poly = clip_polygon(poly, d[:2]-d[2], -d[2])
        area = 0.
        if len(poly) >= 3:
            area = abs(sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(poly, poly[1:]+poly[:1]))) / 2
        regions.append(dict(index=i, fraction=area/.5,
            vertices_hqe=[[float(p[0]), float(p[1]), float(1-p.sum())] for p in poly]))
    return regions
def xy(weights):
    a = np.asarray(weights)
    return np.column_stack((a[:, 0]/2+a[:, 2], HEIGHT*a[:, 0]))
def robust_energy_regions(mx_cost, nv_cost):
    """Same winner at both encoding endpoints implies optimality for every mix."""
    result = []
    for i in range(len(mx_cost)):
        poly = [np.array([1.,0.]), np.array([0.,1.]), np.array([0.,0.])]
        for cost in (mx_cost, nv_cost):
            for j in range(len(mx_cost)):
                if i != j:
                    d = cost[i]-cost[j]
                    poly = clip_polygon(poly, d[:2]-d[2], -d[2])
        area = abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))) if len(poly)>=3 else 0.
        result.append(dict(index=i, fraction=area,
                           vertices_hqe=[[float(p[0]),float(p[1]),float(1-p.sum())] for p in poly]))
    return result
