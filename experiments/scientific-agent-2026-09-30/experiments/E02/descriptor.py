def featurize(s):
    n = max(int(s["n_sites"]), 1)
    v = max(float(s["volume"]), 1e-9)
    lat = np.array(s["lattice"], dtype=float)
    r = np.array(s["covalent_radii"], dtype=float)
    d = np.array(s["neighbor_distance"], dtype=float)
    lens = np.sqrt(np.sum(lat*lat, axis=1))
    lmin = max(float(np.min(lens)), 1e-9)
    lmax = float(np.max(lens))
    cos01 = abs(float(np.sum(lat[0]*lat[1]))) / max(float(lens[0]*lens[1]), 1e-9)
    cos02 = abs(float(np.sum(lat[0]*lat[2]))) / max(float(lens[0]*lens[2]), 1e-9)
    cos12 = abs(float(np.sum(lat[1]*lat[2]))) / max(float(lens[1]*lens[2]), 1e-9)
    pack = (4.0*np.pi/3.0)*float(np.sum(r*r*r))/v
    vpa = v/n
    edge_density = len(d)/n
    close = float(np.sum(d <= 3.0))/n
    meanr = max(float(np.mean(r)), 0.1)
    return {
        "log_volume_per_atom": float(np.log1p(vpa)),
        "log_inverse_packing": float(-np.log(max(pack, 1e-12))),
        "cell_length_anisotropy": lmax/lmin,
        "cell_angle_skew": (cos01+cos02+cos12)/3.0,
        "normalized_spacing": np.power(vpa, 1.0/3.0)/meanr,
        "log_edges6_per_atom": float(np.log1p(edge_density)),
        "log_edges3_per_atom": float(np.log1p(close)),
        "sparse_neighbor_indicator": float(edge_density < 1.0)
    }