Selected candidate: **A05**, under the fixed guard-and-selection rule.

| Candidate | Overall MAE (K) | Positive-Tc MAE (K) | High-Tc MAE (K) | Outcome |
|---|---:|---:|---:|---|
| G01 anchor | 7.9127 | 8.8322 | 32.7716 | Best shared global |
| A01 | 7.8366 | 8.5951 | 28.8039 | Eligible |
| A02 | 7.9112 | 8.9255 | 32.7253 | Guard failure |
| A04 | 8.0417 | 8.4282 | 27.8109 | Guard eligible, worse overall |
| **A05** | **7.7526** | **8.5051** | **28.8502** | **Selected** |

A05 uses composition inputs, fixed chemistry routing, raw-target ExtraTrees globally and for `cu_o`/`other`, with `fe_anion` falling back to the global model. Versus G01:

- Overall MAE improves by 0.1601 K.
- Positive-Tc MAE improves by 0.3271 K.
- RMSE improves from 14.6097 to 13.9945 K.
- High-Tc MAE improves by 3.9214 K.
- Recorded-zero MAE worsens from 5.8697 to 6.0806 K.

The successful revision was A01 → A05: counterexamples exposed severe `cu_o` misses and fold imbalance, but A02 showed that removing the `cu_o` expert lost the positive-Tc guard and high-Tc benefit. Instead, falling the smaller 37-group `fe_anion` route back globally improved A01.

Failed hypotheses:

- A02: global fallback for `cu_o` improved recorded-zero error but violated the positive-Tc guard.
- A04: histogram boosting for `cu_o` improved positive/high-Tc diagnostics but worsened overall and recorded-zero errors.
- A03: no scientific result; the state update failed before fitting and consumed the attempt.
- Global log1p references strongly traded lower recorded-zero error for worse positive/high-Tc prediction, so they did not justify displacing the final routing revision.

G01 also outperformed all four outside-menu structural diagnostics, making it the strongest evaluated global overall. No KMeans candidate was fitted within the five-attempt budget.

These conclusions are predictive training-OOF evidence only. Composition routes are not proven material families, structural matches are proxies, recorded zero does not prove nonsuperconductivity, and no validation outcome is known.