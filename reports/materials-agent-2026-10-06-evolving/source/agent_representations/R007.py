import numpy as np

def compute(structure):
    n = structure["n_sites"]
    centers = np.asarray(structure["neighbor_center"])
    neighbors = np.asarray(structure["neighbor_index"])
    distances = np.asarray(structure["neighbor_distance"])
    images = np.asarray(structure["neighbor_image"])
    frac = np.asarray(structure["frac_coords"])
    lattice = np.asarray(structure["lattice"])
    z = np.asarray(structure["atomic_numbers"])
    radii = np.asarray(structure["covalent_radii"])
    en = np.asarray(structure["electronegativities"])
    sites = np.zeros((n, 6))
    for i in range(n):
        edges = np.where((centers == i) & (distances > 1e-10))[0]
        if len(edges) == 0:
            continue
        ds = distances[edges]
        cutoff = np.sort(ds)[min(11, len(ds) - 1)]
        edges = edges[ds <= cutoff + 1e-8]
        j = neighbors[edges]
        d = distances[edges]
        v = np.dot(frac[j] + images[edges] - frac[i], lattice)
        m = len(edges)
        sums = v[:, None, :] + v[None, :, :]
        costs = np.sum(sums * sums, axis=2) / ((d[:, None] + d[None, :]) ** 2)
        costs = np.clip(costs, 0.0, 1.0)
        distinct = np.eye(m) == 0
        geometric = np.min(np.where(distinct, costs, 1.0), axis=1)
        same = z[j][:, None] == z[j][None, :]
        chemical = np.min(np.where(distinct & same, costs, 1.0), axis=1)
        q = d / np.maximum(radii[i] + radii[j], 1e-8)
        w = np.exp(-q * q)
        w = w / max(float(np.sum(w)), 1e-30)
        gap = np.abs(en[j] - en[i])
        sites[i, 0] = np.sum(w * geometric)
        sites[i, 1] = np.sum(w * geometric * geometric)
        sites[i, 2] = np.sum(w * chemical)
        sites[i, 3] = np.sum(w * chemical * chemical)
        sites[i, 4] = np.sum(w * (chemical - geometric))
        sites[i, 5] = np.sum(w * gap * chemical)
    return np.concatenate((np.mean(sites, axis=0), np.std(sites, axis=0)))
