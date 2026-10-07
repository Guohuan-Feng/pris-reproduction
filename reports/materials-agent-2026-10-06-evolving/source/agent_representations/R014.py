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
    en = np.asarray(structure["electronegativities"])
    values = np.zeros((n, 8))
    for i in range(n):
        edges = np.where(centers == i)[0]
        if len(edges) == 0:
            continue
        ds = distances[edges]
        cutoff = np.sort(ds)[min(11, len(ds) - 1)]
        edges = edges[ds <= cutoff + 1e-8]
        js = indices[edges]
        vectors = np.matmul(frac[js] + images[edges] - frac[i], lattice)
        pos = np.vstack((np.zeros((1, 3)), vectors))
        rr = np.concatenate((radii[i:i+1], radii[js]))
        chi = np.concatenate((en[i:i+1], en[js]))
        chi = chi - np.mean(chi)
        m = len(chi)
        delta = pos[:, None, :] - pos[None, :, :]
        dist2 = np.sum(delta * delta, axis=2)
        rs = rr[:, None] + rr[None, :]
        weights = np.exp(-dist2 / np.maximum(rs * rs, 1e-12)) * (1.0 - np.eye(m))
        hard = 1.0 + 1.0 / np.maximum(rr, 0.1)
        operator = np.diag(hard + np.sum(weights, axis=1)) - weights
        solution = np.linalg.solve(operator, np.column_stack((chi, np.ones(m))))
        u = solution[:, 0]
        v = solution[:, 1]
        response = -u + v * np.sum(u) / np.sum(v)
        free_u = chi / hard
        free_v = 1.0 / hard
        free_response = -free_u + free_v * np.sum(free_u) / np.sum(free_v)
        energy = -np.sum(chi * response) / (2.0 * m)
        free_energy = -np.sum(chi * free_response) / (2.0 * m)
        response_gap = response[:, None] - response[None, :]
        dipole = np.sum(response[:, None] * pos, axis=0) / m
        values[i, 0] = energy
        values[i, 1] = np.sqrt(np.mean(response * response))
        values[i, 2] = np.max(np.abs(response))
        values[i, 3] = response[0]
        values[i, 4] = np.abs(response[0])
        values[i, 5] = np.sum(weights * response_gap * response_gap) / max(np.sum(weights), 1e-12)
        values[i, 6] = np.sqrt(np.sum(dipole * dipole))
        values[i, 7] = free_energy - energy
    return np.concatenate((np.mean(values, axis=0), np.std(values, axis=0)))
