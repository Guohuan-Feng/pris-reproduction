import numpy as np

def compute(structure):
    n = int(structure["n_sites"])
    z = np.asarray(structure["atomic_numbers"])
    r = np.asarray(structure["covalent_radii"])
    centers = np.asarray(structure["neighbor_center"])
    neighbors = np.asarray(structure["neighbor_index"])
    distances = np.asarray(structure["neighbor_distance"])
    sites = np.zeros((n, 7))
    for i in range(n):
        mask = centers == i
        js = neighbors[mask]
        if len(js) == 0:
            continue
        q = distances[mask] / np.maximum(r[i] + r[js], 1e-12)
        order = np.argsort(q)
        q = q[order]
        species = z[js[order]]
        w = np.exp(-q * q)
        total = np.sum(w)
        if total <= 1e-30:
            continue
        p = w / total
        cdf = np.cumsum(p)
        gaps = q[1:] - q[:-1]
        meanq = np.sum(p * q)
        elements = np.unique(species)
        stats = np.zeros((len(elements), 3))
        for k in range(len(elements)):
            select = species == elements[k]
            mass = np.sum(p[select])
            if mass <= 1e-30:
                continue
            conditional = p * select / mass
            transport = np.sum(np.abs(np.cumsum(conditional)[:-1] - cdf[:-1]) * gaps)
            offset = np.sum(conditional * q) - meanq
            stats[k, 0] = mass
            stats[k, 1] = transport
            stats[k, 2] = np.maximum(transport - np.abs(offset), 0.0)
        average = np.sum(stats[:, 0] * stats[:, 1])
        sites[i, 0] = average
        sites[i, 1] = np.sqrt(np.sum(stats[:, 0] * (stats[:, 1] - average) ** 2))
        sites[i, 2] = np.max(stats[:, 1])
        sites[i, 3] = np.sum(stats[:, 0] * stats[:, 2])
        sites[i, 4] = np.max(stats[:, 2])
        same = species == z[i]
        same_mass = np.sum(p[same])
        other_mass = np.sum(p[np.logical_not(same)])
        if same_mass > 1e-30 and other_mass > 1e-30:
            same_p = p * same / same_mass
            other_p = p * (np.logical_not(same)) / other_mass
            sites[i, 5] = np.sum(np.abs(np.cumsum(same_p)[:-1] - np.cumsum(other_p)[:-1]) * gaps)
            sites[i, 6] = np.sum((same_p - other_p) * q)
    if n == 0:
        return np.zeros(14)
    return np.concatenate((np.mean(sites, axis=0), np.std(sites, axis=0)))
