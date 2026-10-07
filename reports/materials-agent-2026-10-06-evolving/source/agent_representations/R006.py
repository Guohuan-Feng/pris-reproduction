import numpy as np

def compute(structure):
    z = np.asarray(structure["atomic_numbers"])
    r = np.asarray(structure["covalent_radii"])
    c = np.asarray(structure["neighbor_center"], dtype=np.int64)
    j = np.asarray(structure["neighbor_index"], dtype=np.int64)
    d = np.asarray(structure["neighbor_distance"])
    n = len(z)
    if n == 0:
        return np.zeros(12)
    species = np.unique(z)
    bulk = np.array([np.mean(z == s) for s in species])
    w = np.exp(-(d / np.maximum(r[c] + r[j], 1e-12)) ** 2)
    local = np.zeros((n, len(species)))
    for k in range(len(species)):
        local[:, k] = np.bincount(c, weights=w * (z[j] == species[k]), minlength=n)
    mass = np.sum(local, axis=1)
    p = local / np.maximum(mass[:, None], 1e-30)
    values = np.zeros((n, 6))
    for i in range(n):
        if mass[i] > 1e-30:
            pi = p[i]
            midpoint = 0.5 * (pi + bulk)
            values[i, 0] = -np.sum(pi * np.log(np.maximum(pi, 1e-30)))
            values[i, 1] = np.sum(pi ** 2)
            values[i, 2] = np.max(pi)
            values[i, 3] = 0.5 * np.sum(pi * np.log(np.maximum(pi, 1e-30) / midpoint)) + 0.5 * np.sum(bulk * np.log(bulk / midpoint))
            values[i, 4] = 0.5 * np.sum(np.abs(pi - bulk))
            values[i, 5] = np.sum((pi - bulk) * (species == z[i]))
    return np.concatenate((np.mean(values, axis=0), np.std(values, axis=0)))
