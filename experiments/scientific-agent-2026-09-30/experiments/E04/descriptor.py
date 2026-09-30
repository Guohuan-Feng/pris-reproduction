def featurize(s):
    n = max(int(s["n_sites"]), 1)
    v = max(float(s["volume"]), 1e-9)
    c = np.array(s["neighbor_center"], dtype=float).astype(int)
    j = np.array(s["neighbor_index"], dtype=float).astype(int)
    d = np.array(s["neighbor_distance"], dtype=float)
    r = np.array(s["covalent_radii"], dtype=float)
    x = np.array(s["electronegativities"], dtype=float)
    finite = np.isfinite(x)
    mx = float(np.nanmean(x)) if np.any(finite) else 0.0
    vx = float(np.nanstd(x))
    coord = np.zeros(n)
    field = np.zeros(n)
    iload = np.zeros(n)
    wr = 0.0
    qsum = 0.0
    rmis = 0.0
    assort = 0.0
    valid = 0.0
    strainion = 0.0
    for k in range(len(d)):
        den = max(r[c[k]] + r[j[k]], 0.1)
        q = d[k]/den
        w = float(np.exp(-np.power(q/1.20, 6.0)))
        coord[c[k]] = coord[c[k]] + w
        wr = wr + w
        qsum = qsum + w*q
        rmis = rmis + w*abs(r[c[k]]-r[j[k]])/den
        if np.isfinite(x[c[k]]) and np.isfinite(x[j[k]]):
            dx = x[j[k]]-x[c[k]]
            field[c[k]] = field[c[k]] + w*dx
            iload[c[k]] = iload[c[k]] + w*abs(dx)
            assort = assort + w*(x[c[k]]-mx)*(x[j[k]]-mx)
            strainion = strainion + w*abs(dx)*abs(q-1.0)
            valid = valid + w
    normfield = np.zeros(n)
    normload = np.zeros(n)
    for i in range(n):
        normfield[i] = field[i]/max(coord[i],1e-6)
        normload[i] = iload[i]/max(coord[i],1e-6)
    mc = float(np.mean(coord))
    covxc = 0.0
    for i in range(n):
        if np.isfinite(x[i]):
            covxc = covxc + (x[i]-mx)*(coord[i]-mc)
    covxc = covxc/max(float(np.sum(finite)),1.0)/max(vx*float(np.std(coord)),1e-6)
    return {
        "log_volume_per_atom": float(np.log1p(v/n)),
        "log_edges6_per_atom": float(np.log1p(len(d)/n)),
        "smooth_coord_mean": wr/n,
        "contact_q_mean": qsum/max(wr,1e-12),
        "site_field_abs_mean": float(np.mean(np.abs(normfield))),
        "site_field_abs_std": float(np.std(np.abs(normfield))),
        "site_ionic_load_mean": float(np.mean(normload)),
        "site_ionic_load_std": float(np.std(normload)),
        "en_coord_correlation": covxc,
        "contact_en_assortativity": assort/max(valid*vx*vx,1e-6),
        "contact_radius_mismatch_mean": rmis/max(wr,1e-12),
        "strain_ionic_coupling": strainion/max(valid,1e-12)
    }