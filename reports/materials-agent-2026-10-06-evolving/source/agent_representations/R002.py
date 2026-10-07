import numpy as np

def compute(structure):
    n = structure["n_sites"]
    center = np.asarray(structure["neighbor_center"], dtype=np.int64)
    other = np.asarray(structure["neighbor_index"], dtype=np.int64)
    d = np.asarray(structure["neighbor_distance"], dtype=np.float64)
    z = np.asarray(structure["atomic_numbers"])
    r = np.asarray(structure["covalent_radii"], dtype=np.float64)
    en = np.asarray(structure["electronegativities"], dtype=np.float64)
    q = d / np.maximum(r[center] + r[other], 0.000001)
    de = en[other] - en[center]
    mismatch = np.abs(r[other] - r[center]) / np.maximum(r[center] + r[other], 0.000001)
    unlike = (z[other] != z[center]).astype(np.float64)
    taper = np.maximum(1.0 - (d / 5.5) ** 2, 0.0) ** 2
    out = np.zeros(24)
    for k in range(3):
        shell = 1.0 + 0.5 * k
        w = np.exp(-0.5 * ((q - shell) / 0.25) ** 2) * taper
        total = np.maximum(np.sum(w), 0.000000000001)
        coord = np.bincount(center, weights=w, minlength=n)
        field = np.bincount(center, weights=w * de, minlength=n)
        load = np.bincount(center, weights=w * np.abs(de), minlength=n)
        out[8*k] = np.mean(coord)
        out[8*k+1] = np.std(coord)
        out[8*k+2] = np.sum(w * unlike) / total
        out[8*k+3] = np.sum(w * np.abs(de)) / total
        out[8*k+4] = np.sum(w * de ** 2) / total
        out[8*k+5] = np.sum(w * mismatch) / total
        out[8*k+6] = np.sqrt(np.mean(field ** 2))
        out[8*k+7] = np.std(load)
    return out
