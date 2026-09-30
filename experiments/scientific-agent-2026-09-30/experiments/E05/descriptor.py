def featurize(s):
    n = max(int(s["n_sites"]),1)
    c = np.array(s["neighbor_center"],dtype=float).astype(int)
    j = np.array(s["neighbor_index"],dtype=float).astype(int)
    d = np.array(s["neighbor_distance"],dtype=float)
    r = np.array(s["covalent_radii"],dtype=float)
    cn115 = np.zeros(n)
    cn135 = np.zeros(n)
    sw = np.zeros(n)
    sq = np.zeros(n)
    sq2 = np.zeros(n)
    for k in range(len(d)):
        q = d[k]/max(r[c[k]]+r[j[k]],0.1)
        if q <= 1.15:
            cn115[c[k]] = cn115[c[k]] + 1.0
        if q <= 1.35:
            cn135[c[k]] = cn135[c[k]] + 1.0
        w = float(np.exp(-np.power(q/1.20,6.0)))
        sw[c[k]] = sw[c[k]] + w
        sq[c[k]] = sq[c[k]] + w*q
        sq2[c[k]] = sq2[c[k]] + w*q*q
    siteq = np.zeros(n)
    distort = np.zeros(n)
    for i in range(n):
        siteq[i] = sq[i]/max(sw[i],1e-12)
        distort[i] = np.sqrt(max(sq2[i]/max(sw[i],1e-12)-siteq[i]*siteq[i],0.0))
    return {
        "cn115_mean": float(np.mean(cn115)),
        "cn115_std": float(np.std(cn115)),
        "cn135_mean": float(np.mean(cn135)),
        "cn135_std": float(np.std(cn135)),
        "smooth_cn_mean": float(np.mean(sw)),
        "smooth_cn_std": float(np.std(sw)),
        "site_q_mean": float(np.mean(siteq)),
        "site_q_std": float(np.std(siteq)),
        "site_distortion_mean": float(np.mean(distort)),
        "site_distortion_std": float(np.std(distort)),
        "undercoord_fraction": float(np.mean(cn135 < 2.0)),
        "highcoord_fraction": float(np.mean(cn135 > 8.0))
    }