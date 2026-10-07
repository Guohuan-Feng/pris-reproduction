import numpy as np

def compute(structure):
    n = structure["n_sites"]
    centers = np.asarray(structure["neighbor_center"])
    indices = np.asarray(structure["neighbor_index"])
    distances = np.asarray(structure["neighbor_distance"])
    images = np.asarray(structure["neighbor_image"])
    frac = np.asarray(structure["frac_coords"])
    lattice = np.asarray(structure["lattice"])
    radii = np.asarray(structure["covalent_radii"])
    numbers = np.asarray(structure["atomic_numbers"])
    site = np.zeros((n, 10))
    for i in range(n):
        edges = np.where(centers == i)[0]
        if len(edges) < 2:
            continue
        cutoff = np.sort(distances[edges])[min(11, len(edges) - 1)]
        edges = edges[distances[edges] <= cutoff + 1e-8]
        js = indices[edges]
        vectors = np.dot(frac[js] + images[edges] - frac[i], lattice)
        m = len(js)
        delta = vectors[:, None, :] - vectors[None, :, :]
        pair_distance = np.sqrt(np.sum(delta * delta, axis=2))
        ratio = pair_distance / np.maximum(radii[js][:, None] + radii[js][None, :], 1e-12)
        adjacency = np.exp(-ratio * ratio) * (1.0 - np.eye(m))
        same = numbers[js][:, None] == numbers[js][None, :]
        for g in range(2):
            a = adjacency if g == 0 else adjacency * same
            degree = np.sum(a, axis=1)
            inv = 1.0 / np.sqrt(np.maximum(degree, 1e-30))
            laplacian = np.diag((degree > 1e-30).astype(float)) - a * inv[:, None] * inv[None, :]
            eig = np.clip(np.linalg.eigvalsh(laplacian), 0.0, 2.0)
            site[i, 5 * g] = np.mean(np.exp(-0.5 * eig))
            site[i, 5 * g + 1] = np.mean(np.exp(-2.0 * eig))
            site[i, 5 * g + 2] = np.mean(np.exp(-8.0 * eig))
            site[i, 5 * g + 3] = np.std(eig)
            site[i, 5 * g + 4] = eig[1]
    return np.concatenate((np.mean(site, axis=0), np.std(site, axis=0)))
