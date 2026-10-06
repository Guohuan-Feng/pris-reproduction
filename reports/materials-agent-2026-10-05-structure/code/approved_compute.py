import numpy as np

def compute(structure):
    neighbors = closest_neighbors(structure)
    numbers = np.asarray(structure["atomic_numbers"])
    n = len(neighbors)
    if n == 0:
        raise ValueError("Structure must contain at least one site")
    if len(numbers) != n:
        raise ValueError("Center and atomic number counts differ")
    histograms = np.zeros((n, 4), dtype=np.float64)
    boundaries = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    for center, vectors in enumerate(neighbors):
        k = len(vectors)
        if k < 2:
            continue
        v = np.asarray(vectors, dtype=np.float64)
        norms = np.sqrt(np.sum(v * v, axis=1))
        unit = v / norms[:, np.newaxis]
        first, second = np.triu_indices(k, 1)
        cosines = np.sum(unit[first] * unit[second], axis=1)
        cosines = np.clip(cosines, -1.0, 1.0)
        for boundary in boundaries:
            cosines = np.where(np.abs(cosines - boundary) <= 1e-10, boundary, cosines)
        counts, edges = np.histogram(cosines, bins=boundaries)
        histograms[center] = counts / float(len(cosines))
    global_mean = np.mean(histograms, axis=0)
    global_variance = np.var(histograms, axis=0, ddof=0)
    nitrogen_mean = np.zeros(4, dtype=np.float64)
    oxygen_mean = np.zeros(4, dtype=np.float64)
    if np.any(numbers == 7):
        nitrogen_mean = np.mean(histograms[numbers == 7], axis=0)
    if np.any(numbers == 8):
        oxygen_mean = np.mean(histograms[numbers == 8], axis=0)
    return np.concatenate((global_mean, global_variance, nitrogen_mean, oxygen_mean)).tolist()
