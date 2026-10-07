import numpy as np

def compute(structure):
    n = structure["n_sites"]
    z = np.asarray(structure["atomic_numbers"])
    en = np.asarray(structure["electronegativities"])
    r = np.asarray(structure["covalent_radii"])
    f = np.asarray(structure["frac_coords"])
    lattice = np.asarray(structure["lattice"])
    center = np.asarray(structure["neighbor_center"])
    neighbor = np.asarray(structure["neighbor_index"])
    distance = np.asarray(structure["neighbor_distance"])
    images = np.asarray(structure["neighbor_image"])
    site = np.zeros((n, 8))
    for i in range(n):
        edges = np.where(center == i)[0]
        if len(edges) < 2:
            continue
        cutoff = np.sort(distance[edges])[min(11, len(edges)-1)]
        edges = edges[distance[edges] <= cutoff + 1e-8]
        j = neighbor[edges]
        d = distance[edges]
        v = np.dot(f[j] + images[edges] - f[i], lattice)
        a, b = np.triu_indices(len(edges), 1)
        sep = np.sqrt(np.sum((v[a] - v[b]) ** 2, axis=1))
        q = d / np.maximum(r[i] + r[j], 1e-8)
        w = np.exp(-q ** 2)
        pair = w[a] * w[b]
        close = np.exp(-(sep / np.maximum(r[j[a]] + r[j[b]], 1e-8)) ** 2)
        motif = pair * close
        denom = max(float(np.sum(motif)), 1e-12)
        site[i, 0] = np.sum(motif) / max(float(np.sum(pair)), 1e-12)
        site[i, 1] = np.log1p(np.sum(motif))
        same = (z[j[a]] == z[i]) & (z[j[b]] == z[i])
        distinct = (z[j[a]] != z[i]) & (z[j[b]] != z[i]) & (z[j[a]] != z[j[b]])
        bridge = (z[j[a]] == z[j[b]]) & (z[j[a]] != z[i])
        site[i, 2] = np.sum(motif * same) / denom
        site[i, 3] = np.sum(motif * distinct) / denom
        site[i, 4] = np.sum(motif * bridge) / denom
        ea = en[j[a]] - en[i]
        eb = en[j[b]] - en[i]
        span = np.maximum(np.maximum(ea, eb), 0.0) - np.minimum(np.minimum(ea, eb), 0.0)
        site[i, 5] = np.sum(motif * span) / denom
        site[i, 6] = np.sum(motif * ea * eb) / denom
        perimeter = q[a] + q[b] + sep / np.maximum(r[j[a]] + r[j[b]], 1e-8)
        site[i, 7] = np.sum(motif * perimeter) / denom
    if n == 0:
        return np.zeros(16)
    return np.concatenate((np.mean(site, axis=0), np.std(site, axis=0)))
