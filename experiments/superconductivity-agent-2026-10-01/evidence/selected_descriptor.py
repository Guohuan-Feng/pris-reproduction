def featurize(s):
    Z = np.array(s["atomic_numbers"],dtype=float)
    X = np.array(s["electronegativities"],dtype=float)
    R = np.array(s["covalent_radii"],dtype=float)
    occ = np.array(s["site_occupancy"],dtype=float)
    fc = np.array(s["frac_coords"],dtype=float)
    lat = np.array(s["lattice"],dtype=float)
    cen = np.array(s["neighbor_center"],dtype=float).astype(int)
    nei = np.array(s["neighbor_index"],dtype=float).astype(int)
    d = np.array(s["neighbor_distance"],dtype=float)
    img = np.array(s["neighbor_image"],dtype=float)
    ss = np.array(s["species_site"],dtype=float).astype(int)
    so = np.array(s["species_occupancy"],dtype=float)
    sr = np.array(s["species_radius"],dtype=float)
    n = len(Z)
    m35 = d<=3.5
    m32 = d<=3.2
    w = occ[cen]*occ[nei]*m35.astype(float)
    sw = np.sum(w)
    ratio = d/np.maximum(R[cen]+R[nei],0.05)
    rm = np.sum(w*ratio)/max(float(sw),1.0)
    rs = np.sqrt(np.sum(w*(ratio-rm)*(ratio-rm))/max(float(sw),1.0))
    validx = np.logical_and(m35,np.logical_and(np.isfinite(X[cen]),np.isfinite(X[nei])))
    wx = occ[cen]*occ[nei]*validx.astype(float)
    xg = np.sum(wx*np.where(validx,np.abs(X[cen]-X[nei])/np.maximum(d,0.2),0.0))/max(float(np.sum(wx)),1.0)
    zg = np.sum(w*np.abs(Z[cen]-Z[nei])/np.maximum(d,0.2))/max(float(sw),1.0)
    disp = fc[nei]+img-fc[cen]
    cx = disp[:,0]*lat[0,0]+disp[:,1]*lat[1,0]+disp[:,2]*lat[2,0]
    cy = disp[:,0]*lat[0,1]+disp[:,1]*lat[1,1]+disp[:,2]*lat[2,1]
    cz = disp[:,0]*lat[0,2]+disp[:,1]*lat[1,2]+disp[:,2]*lat[2,2]
    invd2 = 1.0/np.maximum(d*d,0.04)
    qx = np.sum(w*cx*cx*invd2)/max(float(sw),1.0)
    qy = np.sum(w*cy*cy*invd2)/max(float(sw),1.0)
    qz = np.sum(w*cz*cz*invd2)/max(float(sw),1.0)
    danis = max(qx,qy,qz)-min(qx,qy,qz)
    coord = np.bincount(cen,weights=occ[nei]*m32.astype(float),minlength=n)
    cw = occ/max(float(np.sum(occ)),0.05)
    cm = np.sum(cw*coord)
    cs = np.sqrt(np.sum(cw*(coord-cm)*(coord-cm)))
    nearest = []
    for i in range(n):
        di = d[cen==i]
        if len(di)>0:
            nearest.append(float(np.min(di)))
        else:
            nearest.append(np.nan)
    nearest = np.array(nearest,dtype=float)
    goodn = np.isfinite(nearest)
    swn = np.sum(occ*goodn.astype(float))
    nm = np.sum(occ*np.where(goodn,nearest,0.0))/max(float(swn),1.0)
    ns = np.sqrt(np.sum(occ*goodn.astype(float)*(nearest-nm)*(nearest-nm))/max(float(swn),1.0))
    ent = []
    mixrad = []
    for i in range(n):
        oi = so[ss==i]
        ri = sr[ss==i]
        toi = np.sum(oi)
        if toi>0.0:
            p = oi/toi
            ei = -np.sum(np.where(p>0.0,p*np.log(np.maximum(p,0.00000001)),0.0))
            mr = np.sum(p*ri)
            vr = np.sqrt(np.sum(p*(ri-mr)*(ri-mr)))
            ent.append(float(ei))
            mixrad.append(float(ei*vr))
        else:
            ent.append(0.0)
            mixrad.append(0.0)
    ent = np.array(ent,dtype=float)
    mixrad = np.array(mixrad,dtype=float)
    emean = np.sum(cw*ent)
    emax = np.max(ent)
    emixenv = np.sum(cw*ent*coord)
    rment = np.sum(cw*mixrad)
    return {"new4_bondcount32":float(np.sum(occ[cen]*occ[nei]*m32.astype(float))/max(float(np.sum(occ)),0.05)),
            "new4_bondratio_mean":float(rm),
            "new4_bondratio_std":float(rs),
            "new4_Xgradient":float(xg),
            "new4_Zgradient":float(zg),
            "new4_direction_anis":float(danis),
            "new4_coord_std":float(cs),
            "new4_nearest_mean":float(nm),
            "new4_nearest_std":float(ns),
            "new4_site_mix_entropy_mean":float(emean),
            "new4_site_mix_entropy_max":float(emax),
            "new4_mix_entropy_coord":float(emixenv)}