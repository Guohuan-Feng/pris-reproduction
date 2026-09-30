# Development-audit version provenance

The final-test authorization at **2026-09-30 21:13:47.001871 UTC** records the SHA-256 of the development audit completed at **21:13:22.624499 UTC**. That audit passed 560 checks. A later clarification, written at **21:14:00.712425 UTC**, overwrote the original `audit_development.json` filename after authorization. It separated all previously observed counterexample calls from counterexamples belonging to an explicitly named revision parent. This was an audit narrative change; it did not change experiment code, data, fitted models, selection, predictions or the 560 check results.

The original authorized audit has now been reconstructed in [audit_development_authorized.json](audit_development_authorized.json). Reconstruction restored the original timestamp, original lineage-field layout and Windows CRLF serialization. **The resulting bytes match the SHA-256 recorded in the unchanged authorization exactly:**

`1468de962478fafded724b101c15b7c7a78fc6530ea48da78c9f948ccdd554c5`

This is a hash-verified reconstruction, not a claim that an untouched backup had existed. The clarified [audit_development.json](audit_development.json) remains available with SHA-256:

`9c1e46d66b0dbf7c2606b5f078786627bc918732b373582d46cabbac102d6f57`

The clarification matters for interpretation: E04 explicitly names E03 as its revision parent and follows E03 counterexample calls 9 and 10. E02, E03 and E05 name no revision parent. They had observed earlier feedback, but that observation does not establish a formal parent relationship.

Independent byte-level verification after recovery confirmed:

- All four prepared source hashes match: features, development labels, split assignments and sealed test labels. The test label file was hashed as bytes for this verification; no new target evaluation was performed.
- All 65 development-artifact hashes recorded at selection still match.
- The evaluator source hash still matches its prepared manifest.
- The selection hash, frozen test-prediction hash, prediction-freeze hash in the test-access marker and selected E04 test-descriptor hash all match their recorded values.
- The authorized and clarified development audits contain identical lists of 560 checks.
- [audit_final.json](audit_final.json) remains unchanged and records 715 passing checks, including independent numerical prediction, metric and paired-bootstrap replay.

Neither [FINAL_EVALUATION_AUTHORIZATION.json](FINAL_EVALUATION_AUTHORIZATION.json) nor [TEST_ACCESS_STARTED.json](evaluation/final/TEST_ACCESS_STARTED.json) was modified during recovery. Their SHA-256 values are respectively:

`bb7470266754313fdbe5536d417ce6f5bf7806f822a35f2871ce8533842f1dbe`

`62cdb9a2cf70ef4b30927227ea8d5805eb18253f757ba15e00690f386a157fab`

The unchanged final-audit SHA-256 is:

`46a27a1210c79c24a8452cb67dd12e89c29255a5b47fa35423086d84534ce0d9`

# 开发审计版本来源说明

**2026年9月30日21:13:47.001871 UTC**的最终测试授权，记录的是**21:13:22.624499 UTC**完成的开发审计哈希，该版本通过560项检查。随后在**21:14:00.712425 UTC**进行的文字澄清覆盖了原来的`audit_development.json`文件名。澄清将“此前观察过的全部反例调用”与“明确修订母实验的反例调用”分开列示。此次变动仅涉及审计叙述，未改变实验代码、数据、拟合模型、选择、预测或560项检查结果。

授权时的原始审计现已重建并保存为[audit_development_authorized.json](audit_development_authorized.json)。重建恢复了原始时间戳、修订关系字段及Windows CRLF换行格式，**文件字节的SHA-256与未修改的授权记录完全一致**。这是经过哈希核验的重建，不表示此前一直存在未改动的备份。澄清后的[audit_development.json](audit_development.json)仍单独保留；两者哈希见上文。

该澄清的解释意义是：E04明确以E03为修订母实验，发生在E03的第9、10次反例调用之后；E02、E03及E05没有声明修订母实验。它们此前观察过反馈，不等于存在正式的母实验关系。

重建后独立核验确认：4份准备阶段源文件、选择时冻结的65份开发产物、评估器代码、选择记录、冻结测试预测、测试读取标记引用的预测冻结记录，以及E04测试描述符的哈希均仍匹配。两个开发审计版本的560项检查列表完全一致。原有最终审计未改动，仍记录715项检查全部通过。此次仅进行了文件字节核验，没有重新拟合、调参或评估测试标签。原始授权及测试读取标记均保持不变。
