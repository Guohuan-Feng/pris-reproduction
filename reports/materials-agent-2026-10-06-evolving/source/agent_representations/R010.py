import numpy as np

def compute(structure):
    n = structure["n_sites"]
    z = np.asarray(structure["atomic_numbers"])
    en = np.asarray(structure["electronegativities"])
    r = np.asarray(structure["covalent_radii"])
    centers = np.asarray(structure["neighbor_center"])
    indices = np.asarray(structure["neighbor_index"])
    distances = np.asarray(structure["neighbor_distance"])
    images = np.asarray(structure["neighbor_image"])
    frac = np.asarray(structure["frac_coords"])
    lattice = np.asarray(structure["lattice"])
    sites = np.zeros((n, 8))
    for i in range(n):
        edges = np.where((centers == i) & (distances > 1e-10))[0]
        if len(edges) < 3:
            continue
        ds = distances[edges]
        cutoff = np.sort(ds)[min(11, len(ds) - 1)]
        edges = edges[ds <= cutoff + 1e-8]
        js = indices[edges]
        ds = distances[edges]
        v = (frac[js] + images[edges] - frac[i]) @ lattice
        u = v / ds[:, None]
        w = np.exp(-(ds / np.maximum(r[i] + r[js], 1e-8)) ** 2)
        m = len(edges)
        triples = np.asarray([[a, b, c] for a in range(m) for b in range(a + 1, m) for c in range(b + 1, m)])
        a = triples[:, 0]
        b = triples[:, 1]
        c = triples[:, 2]
        vol = np.clip(np.abs(np.sum(u[a] * np.cross(u[b], u[c]), axis=1)), 0.0, 1.0)
        wt = w[a] * w[b] * w[c]
        total = np.sum(wt)
        if total <= 1e-30:
            continue
        wt = wt / total
        za = z[js[a]]
        zb = z[js[b]]
        zc = z[js[c]]
        same = (za == zb) & (zb == zc)
        distinct = (za != zb) & (za != zc) & (zb != zc)
        unlike = (za != z[i]) & (zb != z[i]) & (zc != z[i])
        ea = en[js[a]]
        eb = en[js[b]]
        ec = en[js[c]]
        span = np.maximum(np.maximum(ea, eb), np.maximum(ec, en[i])) - np.minimum(np.minimum(ea, eb), np.minimum(ec, en[i]))
        mean = np.sum(wt * vol)
        sites[i, 0] = mean
        sites[i, 1] = np.sum(wt * vol ** 3)
        sites[i, 2] = np.sum(wt * np.exp(-10.0 * vol))
        sites[i, 3] = np.sum(wt * vol * same)
        sites[i, 4] = np.sum(wt * vol * distinct)
        sites[i, 5] = np.sum(wt * vol * unlike)
        sites[i, 6] = np.sum(wt * vol * span)
        sites[i, 7] = np.sqrt(np.maximum(np.sum(wt * (vol - mean) ** 2), 0.0))
    return np.concatenate((np.mean(sites, axis=0), np.std(sites, axis=0)))
