def featurize(s):
    n = int(s["n_sites"])
    c = np.array(s["neighbor_center"], dtype=float).astype(int)
    j = np.array(s["neighbor_index"], dtype=float).astype(int)
    d = np.array(s["neighbor_distance"], dtype=float)
    r = np.array(s["covalent_radii"], dtype=float)
    x = np.array(s["electronegativities"], dtype=float)
    z = np.array(s["atomic_numbers"], dtype=float)
    coord = np.zeros(n)
    wsum = 0.0
    qsum = 0.0
    q2sum = 0.0
    dxsum = 0.0
    dx2sum = 0.0
    zxsum = 0.0
    heterosum = 0.0
    validx = 0.0
    for k in range(len(d)):
        den = r[c[k]] + r[j[k]]
        q = d[k] / max(den, 0.1)
        w = float(np.exp(-np.power(q / 1.20, 6.0)))
        coord[c[k]] = coord[c[k]] + w
        wsum = wsum + w
        qsum = qsum + w*q
        q2sum = q2sum + w*q*q
        if z[c[k]] != z[j[k]]:
            heterosum = heterosum + w
        if np.isfinite(x[c[k]]) and np.isfinite(x[j[k]]):
            dx = abs(x[c[k]] - x[j[k]])
            dxsum = dxsum + w*dx
            dx2sum = dx2sum + w*dx*dx
            zxsum = zxsum + w*dx/max(q, 0.25)
            validx = validx + w
    mq = qsum / max(wsum, 1e-12)
    mdx = dxsum / max(validx, 1e-12)
    return {
        "smooth_coord_mean": wsum / max(n, 1),
        "smooth_coord_std": float(np.std(coord)),
        "smooth_coord_cv": float(np.std(coord)) / max(float(np.mean(coord)), 1e-6),
        "contact_q_mean": mq,
        "contact_q_std": float(np.sqrt(max(q2sum/max(wsum,1e-12)-mq*mq, 0.0))),
        "bond_dx_mean": mdx,
        "bond_dx_std": float(np.sqrt(max(dx2sum/max(validx,1e-12)-mdx*mdx, 0.0))),
        "ionic_contact_index": zxsum / max(validx, 1e-12),
        "heterocontact_fraction": heterosum / max(wsum, 1e-12),
        "coord_low_fraction": float(np.mean(coord < 1.5))
    }