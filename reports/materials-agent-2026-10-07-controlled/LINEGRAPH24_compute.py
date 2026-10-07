import numpy as np


def compute(structure):
    n = int(structure["n_sites"])
    site_powers = np.zeros((n, 12), dtype=float)
    center = np.asarray(structure["neighbor_center"], dtype=int)
    neighbor = np.asarray(structure["neighbor_index"], dtype=int)
    image = np.asarray(structure["neighbor_image"], dtype=float).reshape((-1, 3))
    if len(center) == 0:
        return np.zeros(24, dtype=float).tolist()
    frac = np.asarray(structure["frac_coords"], dtype=float)
    lattice = np.asarray(structure["lattice"], dtype=float)
    radii = np.asarray(structure["covalent_radii"], dtype=float)
    en = np.asarray(structure["electronegativities"], dtype=float)
    atomic_numbers = np.asarray(structure["atomic_numbers"], dtype=int)
    relative = (frac[neighbor] + image - frac[center]) @ lattice
    distance = np.sqrt(np.sum(relative * relative, axis=1))
    valid = distance > 1e-10
    center = center[valid]
    neighbor = neighbor[valid]
    relative = relative[valid]
    distance = distance[valid]
    directions = relative / distance[:, None]
    radial = np.exp(-np.power(distance / (radii[center] + radii[neighbor]), 2))
    en_valid = (en[center] > 0) & (en[neighbor] > 0)
    en_ratio = np.where(en_valid, (en[neighbor] - en[center]) / np.maximum(en[neighbor] + en[center], 1e-12), 0.0)
    radius_ratio = (radii[neighbor] - radii[center]) / (radii[neighbor] + radii[center])
    unlike = (atomic_numbers[neighbor] != atomic_numbers[center]).astype(float)
    channels = np.column_stack((np.ones(len(center)), en_ratio, radius_ratio, unlike))
    for site in range(n):
        mask = center == site
        if not np.any(mask):
            continue
        weight_sum = float(np.sum(radial[mask]))
        if weight_sum <= 0:
            continue
        u = directions[mask]
        weighted = radial[mask, None] * channels[mask] / weight_sum
        first = weighted.T @ u
        second = np.einsum("ec,ei,ej->cij", weighted, u, u)
        third = np.einsum("ec,ei,ej,ek->cijk", weighted, u, u, u)
        amplitude = np.sum(weighted, axis=0)
        first_norm = np.sum(first * first, axis=1)
        second_norm = np.sum(second * second, axis=(1, 2))
        third_norm = np.sum(third * third, axis=(1, 2, 3))
        power1 = first_norm
        power2 = (3.0 * second_norm - amplitude * amplitude) / 2.0
        power3 = (5.0 * third_norm - 3.0 * first_norm) / 2.0
        site_powers[site] = np.maximum(np.column_stack((power1, power2, power3)).reshape(12), 0.0)
    return np.concatenate((np.mean(site_powers, axis=0), np.std(site_powers, axis=0))).tolist()
