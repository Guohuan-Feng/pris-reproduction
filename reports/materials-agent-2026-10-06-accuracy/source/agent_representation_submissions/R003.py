import numpy as np

def compute(structure):
    n = int(structure["n_sites"])
    c = np.asarray(structure["neighbor_center"], dtype=np.int64)
    j = np.asarray(structure["neighbor_index"], dtype=np.int64)
    d = np.asarray(structure["neighbor_distance"], dtype=float)
    im = np.asarray(structure["neighbor_image"], dtype=float).reshape((-1, 3))
    f = np.asarray(structure["frac_coords"], dtype=float)
    lat = np.asarray(structure["lattice"], dtype=float)
    en = np.asarray(structure["electronegativities"], dtype=float)
    rad = np.asarray(structure["covalent_radii"], dtype=float)
    vec = np.dot(f[j] + im - f[c], lat)
    unit = vec / np.maximum(d[:, None], 1e-12)
    rho = d / np.maximum(rad[c] + rad[j], 1e-6)
    dc = en[j] - en[c]
    w = np.exp(-np.minimum(rho, 8.0)**2)
    out = np.zeros((n, 4))
    for i in range(n):
        mask = (c == i) & (d > 1e-8)
        wi = w[mask]
        sw = np.sum(wi)
        if sw > 1e-12:
            p = wi / sw
            ri = rho[mask]
            qi = dc[mask]
            ui = unit[mask]
            rc = ri - np.sum(p * ri)
            qc = qi - np.sum(p * qi)
            a = np.sum((p * qi)[:, None] * ui, axis=0)
            b = np.sum((p * qi * rc)[:, None] * ui, axis=0)
            out[i, 0] = np.sum(p * rc * qc)
            out[i, 1] = np.sum(p * rc * rc * qc)
            out[i, 2] = np.dot(b, b)
            out[i, 3] = np.dot(a, b)
    return np.concatenate((np.mean(out, axis=0), np.std(out, axis=0))).tolist()
