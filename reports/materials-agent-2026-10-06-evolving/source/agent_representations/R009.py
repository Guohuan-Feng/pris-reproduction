import numpy as np

def compute(structure):
    n = int(structure["n_sites"])
    out = np.zeros(14)
    if n == 0:
        return out
    center = np.asarray(structure["neighbor_center"], dtype=np.int64)
    neighbor = np.asarray(structure["neighbor_index"], dtype=np.int64)
    distance = np.asarray(structure["neighbor_distance"], dtype=float)
    if len(distance) == 0:
        return out
    z = np.asarray(structure["atomic_numbers"], dtype=np.int64)
    radius = np.asarray(structure["covalent_radii"], dtype=float)
    q = distance / np.maximum(radius[center] + radius[neighbor], 1e-12)
    w = np.exp(-((q / 1.5) ** 6))
    total = float(np.sum(w))
    if total <= 0.0:
        return out
    pair = np.minimum(z[center], z[neighbor]) * 1000 + np.maximum(z[center], z[neighbor])
    pair_mean = np.zeros(len(distance))
    pair_var = np.zeros(len(distance))
    for p in np.unique(pair):
        mask = pair == p
        wp = w[mask]
        qp = q[mask]
        mass = float(np.sum(wp))
        if mass > 0.0:
            mu = np.sum(wp * qp) / mass
            variance = np.sum(wp * (qp - mu) ** 2) / mass
            pair_mean[mask] = mu
            pair_var[mask] = variance
    residual = q - pair_mean
    overall = np.sum(w * q) / total
    within = np.sum(w * residual ** 2) / total
    out[0] = overall
    out[1] = within
    out[2] = np.sum(w * (pair_mean - overall) ** 2) / total
    out[3] = np.sum(w * residual ** 3) / total
    out[4] = np.sum(w * residual ** 4) / total
    out[5] = np.sum(w * (pair_var - within) ** 2) / total
    values = np.column_stack((np.abs(residual), residual ** 2, np.maximum(1.0 - q, 0.0), np.maximum(q - 1.0, 0.0)))
    site = np.zeros((n, 4))
    for i in range(n):
        mask = center == i
        wi = w[mask]
        mass = float(np.sum(wi))
        if mass > 0.0:
            site[i] = np.sum(wi[:, None] * values[mask], axis=0) / mass
    out[6:10] = np.mean(site, axis=0)
    out[10:14] = np.std(site, axis=0)
    return out
