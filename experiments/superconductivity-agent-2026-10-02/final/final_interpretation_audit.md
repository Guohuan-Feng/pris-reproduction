# Frozen Tc V2 result interpretation audit

This file transcribes the protocol auditor's confirmed read-only findings, recorded by the primary collaborator after scoring. No specification, selection, numerical result or frozen scientific file was changed.

- A05 old-validation MAE is 8.0848868700 K versus the shared global G01 at 8.0885438119 K: a reduction of 0.0036569419 K (0.0452%). The conditional paired-group 95% interval [-0.1947969146, +0.1506968026] K crosses zero. This is essentially a tie, not a reliable incremental Agent benefit.
- Positive-Tc MAE worsens from 10.1449285831 to 10.1957398266 K. Recorded-zero MAE improves from 3.0222087504 to 2.8843580133 K. High-Tc MAE improves from 37.3135057236 to 36.4197154795 K, but the subgroup contains only 35 rows in nine strict groups and remains underpredicted. RMSE slightly worsens from 15.5449948601 to 15.5495600036 K.
- The predeclared outside-menu 11-descriptor reference D01 has lower validation MAE, 7.9427320240 K. A05 minus D01 is +0.1421548460 K with conditional interval [-0.4651294210, +0.7206785403] K. D01 did not win training OOF; it is a fixed diagnostic, not a post-validation replacement winner.
- Automated search retained G01, so Agent versus automated and Agent versus shared global are the same fitted comparison. Their identical intervals are not separate confirmations.
- Conventional target choice provides the larger development change: G01 raw Tc versus the V2 G02 log1p reference changes validation MAE from 8.7599287483 to 8.0885438119 K. That gain does not belong to the added autonomous routing intervention. Recorded-zero MAE worsens from 1.2315749985 to 3.0222087504 K in that target comparison.
- The original 869 validation rows were inspected historically. The conditional bootstrap does not include training/search/prior-inspection uncertainty. No fresh independent evaluation, new superconductors or established physical mechanism follows from this pilot. The original 1,140 retrospective targets were not used this round.

The independent numerical verifier passed 5,092 checks and replayed all 21 saved models with maximum prediction difference 0 K. Administrative audit separately confirms five attempted Agent configurations, four successful pipelines, one disclosed pre-fit A03 infrastructure failure, and the unchanged five-configuration automated plan.
