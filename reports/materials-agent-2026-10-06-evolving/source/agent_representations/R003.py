import numpy as np

def compute(structure):
    n = int(structure["n_sites"])
    local = np.zeros((n, 8))
    center = np.asarray(structure["neighbor_center"], dtype=np.int64)
    index = np.asarray(structure["neighbor_index"], dtype=np.int64)
    distance = np.asarray(structure["neighbor_distance"], dtype=np.float64)
    frac = np.asarray(structure["frac_coords"], dtype=np.float64)
    lattice = np.asarray(structure["lattice"], dtype=np.float64)
    images = np.asarray(structure["neighbor_image"], dtype=np.float64)
    radii = np.asarray(structure["covalent_radii"], dtype=np.float64)
    en = np.asarray(structure["electronegativities"], dtype=np.float64)
    if n == 0:
        return np.zeros(16)
    for i in range(n):
        mask = (center == i) & (distance > 1e-10) & (distance < 6.0)
        j = index[mask]
        if len(j) > 0:
            v = np.dot(frac[j] + images[mask] - frac[i], lattice)
            d = distance[mask]
            u = v / d[:, None]
            ratio = d / np.maximum(radii[i] + radii[j], 1e-8)
            w = np.exp(-ratio * ratio) * (1.0 - d / 6.0) ** 2
            wc = w * np.abs(en[j] - en[i])
            g = np.zeros((3, 3))
            c = np.zeros((3, 3))
            if np.sum(w) > 1e-14:
                g = np.dot(u.T, w[:, None] * u) / np.sum(w)
                local[i, 0:3] = np.linalg.eigvalsh(g)
            if np.sum(wc) > 1e-14:
                c = np.dot(u.T, wc[:, None] * u) / np.sum(wc)
                local[i, 3:6] = np.linalg.eigvalsh(c)
                local[i, 6] = np.sum(g * c)
                local[i, 7] = np.sum((g - c) ** 2)
    return np.concatenate((np.mean(local, axis=0), np.std(local, axis=0)))
