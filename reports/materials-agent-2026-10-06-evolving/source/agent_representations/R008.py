import numpy as np

def compute(structure):
    cages = closest_neighbors(structure)
    values = np.zeros((structure["n_sites"], 4))
    for i in range(structure["n_sites"]):
        vectors = np.asarray(cages[i], dtype=np.float64)
        if len(vectors) == 0:
            continue
        lengths = np.sqrt(np.sum(vectors * vectors, axis=1))
        vectors = vectors[lengths > 1e-12]
        lengths = lengths[lengths > 1e-12]
        if len(lengths) == 0:
            continue
        u = vectors / lengths[:, None]
        a, b = np.triu_indices(len(u), 1)
        sums = -(u[a] + u[b])
        normals = np.cross(u[a], u[b])
        probes = np.concatenate((-u, sums, normals, -normals), axis=0)
        norms = np.sqrt(np.sum(probes * probes, axis=1))
        probes = probes[norms > 1e-10]
        norms = norms[norms > 1e-10]
        probes = probes / norms[:, None]
        clearance = 0.5 * (1.0 - np.clip(np.max(np.dot(probes, u.T), axis=1), -1.0, 1.0))
        values[i, 0] = np.max(clearance)
        values[i, 1] = np.mean(clearance)
        values[i, 2] = np.std(clearance)
        values[i, 3] = np.quantile(clearance, 0.75)
    return np.concatenate((np.mean(values, axis=0), np.std(values, axis=0)))
