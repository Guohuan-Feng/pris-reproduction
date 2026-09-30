## Scientific development report

Five experiments were completed; **E04 was selected for both tasks** based on adaptive validation.

| Experiment | Main descriptor hypothesis | Formation MAE | Hull logloss |
|---|---|---:|---:|
| raw30 | Fixed baseline | 0.34253 | 0.56585 |
| E01 | Smooth local bond geometry | 0.31902 | 0.55956 |
| E02 | Robust cell openness | 0.32463 | 0.56197 |
| E03 | Site-resolved chemical fields | 0.31134 | 0.55275 |
| **E04** | **E03 revised with openness controls** | **0.30159** | **0.55264** |
| E05 | Coordination-topology ablation | 0.33772 | 0.56277 |

E04’s 12 invented descriptors combine:

- `log1p(volume/N)` and `log1p(E_6Å/N)`
- Smooth coordination and mean normalized contact length
- Site-resolved electronegativity fields and ionic loads
- Electronegativity–coordination correlation
- Contact electronegativity assortativity
- Covalent-radius mismatch
- Bond-strain/electronegativity coupling

Periodic edges were weighted by  
\(w=\exp[-(q/1.20)^6]\), where \(q=d/(r_{\mathrm{cov},i}+r_{\mathrm{cov},j})\). Covalent radii were strictly geometric scales, not ionic radii or oxidation-state estimates.

Counterexamples changed the work materially: E03’s largest formation errors still included ultra-open cells with roughly 1,039–1,312 Å³/atom and extremely sparse neighbor graphs. E04 therefore revised E03 by adding log-scaled openness and contact-regime controls. This reduced development MAE by another 0.00975 eV/atom, while hull improvement over E03 was only 0.00011.

E02 showed that openness alone was insufficient. E05 showed that hard coordination counts and bond-length distortion alone were much weaker than chemistry–environment coupling.

These are adaptive validation results, not test results. E04 also remains worse than the separate nonlinear raw30 HGB reference on development data—0.27279 formation MAE and 0.54317 hull logloss—so the evidence supports improvement over the evaluated raw30 arm, not universal superiority. Unseen chemical-system generalization, the chosen numerical cutoffs, unusual open-cell behavior, competing-phase information for hull prediction, oxidation states, magnetism, and electronic effects remain unverified.