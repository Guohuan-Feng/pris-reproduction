import numpy as np

def compute(structure):
    n = int(structure["n_sites"])
    center = np.asarray(structure["neighbor_center"], dtype=np.int64)
    index = np.asarray(structure["neighbor_index"], dtype=np.int64)
    images = np.asarray(structure["neighbor_image"], dtype=np.float64)
    frac = np.asarray(structure["frac_coords"], dtype=np.float64)
    lattice = np.asarray(structure["lattice"], dtype=np.float64)
    radii = np.asarray(structure["covalent_radii"], dtype=np.float64)
    en = np.asarray(structure["electronegativities"], dtype=np.float64)
    vectors = np.dot(frac[index] + images - frac[center], lattice)
    distance = np.sqrt(np.sum(vectors * vectors, axis=1))
    local = np.zeros((n, 6))
    for i in range(n):
        mask = (center == i) & (distance > 1.0e-8)
        d = distance[mask]
        j = index[mask]
        u = vectors[mask] / d[:, None]
        q = d / np.maximum(radii[i] + radii[j], 0.1)
        w = np.exp(-q * q)
        total = np.sum(w) + 1.0e-15
        p = w / total
        contrast = en[j] - en[i]
        c2 = contrast * contrast
        chemical = p * c2
        mass = np.sum(chemical) + 1.0e-12
        pc = chemical / mass
        geom = np.einsum("i,ij,ik->jk", p, u, u)
        chem = np.einsum("i,ij,ik->jk", pc, u, u)
        dipole = np.sum((p * contrast)[:, None] * u, axis=0)
        commutator = np.dot(geom, chem) - np.dot(chem, geom)
        qmean = np.sum(pc * q)
        qbase = np.sum(p * q)
        cmean = np.sum(p * contrast)
        local[i, 0] = np.sum(dipole * dipole)
        local[i, 1] = np.sum((chem - np.eye(3) * np.trace(chem) / 3.0) ** 2)
        local[i, 2] = np.sum((chem - geom) ** 2)
        local[i, 3] = np.sum(commutator * commutator)
        local[i, 4] = np.sum(pc * (q - qmean) ** 2) / (qmean * qmean + 1.0e-12)
        local[i, 5] = np.sum(p * (q - qbase) * (contrast - cmean))
    return np.concatenate((np.mean(local, axis=0), np.std(local, axis=0)))
