import numpy as np

def compute(structure):
    n = structure["n_sites"]
    c = np.asarray(structure["neighbor_center"], dtype=np.int64)
    j = np.asarray(structure["neighbor_index"], dtype=np.int64)
    d = np.asarray(structure["neighbor_distance"])
    r = np.asarray(structure["covalent_radii"])
    en = np.asarray(structure["electronegativities"])
    z = np.asarray(structure["atomic_numbers"])
    q = d / np.maximum(r[c] + r[j], 1e-12)
    w = np.exp(-q * q) * np.maximum(1.0 - d / 6.0, 0.0) ** 2
    degree = np.bincount(c, weights=w, minlength=n)
    den = np.maximum(degree, 1e-12)
    active = degree > 1e-12
    h = np.zeros((n, 4))
    h[:, 0] = np.log1p(degree)
    h[:, 1] = np.bincount(c, weights=w * en[j], minlength=n) / den
    second = np.bincount(c, weights=w * en[j] ** 2, minlength=n) / den
    h[:, 2] = np.maximum(second - h[:, 1] ** 2, 0.0)
    h[:, 3] = np.bincount(c, weights=w * (z[c] != z[j]), minlength=n) / den
    out = np.zeros(24)
    for k in range(4):
        a = h[:, k]
        b = np.bincount(c, weights=w * a[j], minlength=n) / den
        v = np.maximum(np.bincount(c, weights=w * a[j] ** 2, minlength=n) / den - b * b, 0.0)
        contrast = np.bincount(c, weights=w * (a[c] - a[j]) ** 2, minlength=n) / den
        center = np.mean(a)
        covariance = (a - center) * (b - center) * active
        out[6 * k] = np.mean(b)
        out[6 * k + 1] = np.std(b)
        out[6 * k + 2] = np.mean(contrast)
        out[6 * k + 3] = np.std(contrast)
        out[6 * k + 4] = np.mean(v)
        out[6 * k + 5] = np.mean(covariance)
    return out
