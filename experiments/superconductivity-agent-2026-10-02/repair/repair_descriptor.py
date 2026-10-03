def featurize(s):
    Z = np.array(s["atomic_numbers"], dtype=float)
    X = np.array(s["electronegativities"], dtype=float)
    R = np.array(s["covalent_radii"], dtype=float)
    occ = np.array(s["site_occupancy"], dtype=float)
    fc = np.array(s["frac_coords"], dtype=float)
    lat = np.array(s["lattice"], dtype=float)
    cen = np.array(s["neighbor_center"], dtype=float).astype(int)
    nei = np.array(s["neighbor_index"], dtype=float).astype(int)
    d = np.array(s["neighbor_distance"], dtype=float)
    img = np.array(s["neighbor_image"], dtype=float).reshape(-1, 3)
    ss = np.array(s["species_site"], dtype=float).astype(int)
    so = np.array(s["species_occupancy"], dtype=float)
    sr = np.array(s["species_radius"], dtype=float)
    n = len(Z)
    m35 = d <= 3.5
    m32 = d <= 3.2
    w = occ[cen] * occ[nei] * m35.astype(float)
    sw = float(np.sum(w))
    ratio = d / np.maximum(R[cen] + R[nei], 0.05)
    rm = np.sum(w * ratio) / sw if sw > 0.0 else np.nan
    rs = np.sqrt(np.sum(w * (ratio - rm) * (ratio - rm)) / sw) if sw > 0.0 else np.nan
    validx = np.logical_and(m35, np.logical_and(np.isfinite(X[cen]), np.isfinite(X[nei])))
    wx = occ[cen] * occ[nei] * validx.astype(float)
    sx = float(np.sum(wx))
    xg = np.sum(wx * np.where(validx, np.abs(X[cen] - X[nei]) / np.maximum(d, 0.2), 0.0)) / sx if sx > 0.0 else np.nan
    zg = np.sum(w * np.abs(Z[cen] - Z[nei]) / np.maximum(d, 0.2)) / sw if sw > 0.0 else np.nan
    disp = fc[nei] + img - fc[cen]
    cx = disp[:, 0] * lat[0, 0] + disp[:, 1] * lat[1, 0] + disp[:, 2] * lat[2, 0]
    cy = disp[:, 0] * lat[0, 1] + disp[:, 1] * lat[1, 1] + disp[:, 2] * lat[2, 1]
    cz = disp[:, 0] * lat[0, 2] + disp[:, 1] * lat[1, 2] + disp[:, 2] * lat[2, 2]
    if sw > 0.0:
        invd2 = 1.0 / (d * d)
        qxx = np.sum(w * cx * cx * invd2) / sw
        qyy = np.sum(w * cy * cy * invd2) / sw
        qzz = np.sum(w * cz * cz * invd2) / sw
        qxy = np.sum(w * cx * cy * invd2) / sw
        qxz = np.sum(w * cx * cz * invd2) / sw
        qyz = np.sum(w * cy * cz * invd2) / sw
        traceq2 = qxx * qxx + qyy * qyy + qzz * qzz + 2.0 * (qxy * qxy + qxz * qxz + qyz * qyz)
        danis = float(np.clip((3.0 * traceq2 - 1.0) / 2.0, 0.0, 1.0))
    else:
        danis = np.nan
    total_occ = float(np.sum(occ))
    cw = occ / total_occ
    coord = np.bincount(cen, weights=occ[nei] * m32.astype(float), minlength=n)
    cm = np.sum(cw * coord)
    cs = np.sqrt(np.sum(cw * (coord - cm) * (coord - cm)))
    nearest = []
    for i in range(n):
        di = d[cen == i]
        nearest.append(float(np.min(di)) if len(di) > 0 else np.nan)
    nearest = np.array(nearest, dtype=float)
    goodn = np.isfinite(nearest)
    swn = float(np.sum(occ * goodn.astype(float)))
    nm = np.sum(occ * np.where(goodn, nearest, 0.0)) / swn if swn > 0.0 else np.nan
    ns = np.sqrt(np.sum(occ * np.where(goodn, (nearest - nm) * (nearest - nm), 0.0)) / swn) if swn > 0.0 else np.nan
    ent = []
    for i in range(n):
        oi = so[ss == i]
        toi = float(np.sum(oi))
        p = oi / toi
        ei = -np.sum(np.where(p > 0.0, p * np.log(np.maximum(p, 0.00000001)), 0.0))
        ent.append(float(ei))
    ent = np.array(ent, dtype=float)
    return {"new4_bondcount32": float(np.sum(occ[cen] * occ[nei] * m32.astype(float)) / total_occ),
            "new4_bondratio_mean": float(rm),
            "new4_bondratio_std": float(rs),
            "new4_Xgradient": float(xg),
            "new4_Zgradient": float(zg),
            "new4_direction_anis_invariant": float(danis),
            "new4_coord_std": float(cs),
            "new4_nearest_mean": float(nm),
            "new4_nearest_std": float(ns),
            "new4_site_mix_entropy_mean": float(np.sum(cw * ent)),
            "new4_site_mix_entropy_max": float(np.max(ent)),
            "new4_mix_entropy_coord": float(np.sum(cw * ent * coord))}
