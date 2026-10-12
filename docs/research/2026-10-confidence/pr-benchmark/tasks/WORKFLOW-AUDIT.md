# Retrospective public-workflow routing audit

The submitted `current_cp_06` implementation passes all seven independently executed public-workflow cases below, while the frozen primary oracle grades it RED. This confirms an internal partition constraint in that primary oracle relative to these cases: it requires `AppServerPhaseDriver.observe_notification` itself to suppress foreign completions, whereas this submission puts the active-thread/turn filter in `run_phase`. This conclusion does not establish correctness outside this matrix.

This is **RETROSPECTIVE SECONDARY** evidence. The first three primary outcomes and submitted patches had already been examined when this audit was proposed. Its case matrix was specified by the coordinator, and the new source was frozen before running any secondary controls or candidate evaluations. The original 84 requests, primary oracles, grade receipts, and comparisons remain intact. No outcomes or hints were supplied to solvers, no trials were retried, and this audit does not replace primary scores.

## Fixed cases and boundary

All cases call the actual `run_phase` implementation with actual native driver construction, a deterministic line-oriented app-server process fixture, and a resumed coordinator session. They never call or assert the return shape of `observe_notification`, and do not initialize new private fields. A foreign completion is inserted after the `turn/start` response and before the legitimate receipt, so the check observes whether the entire phase still returns the correct coordinator receipt.

1. Wrong thread, active turn: ignore the foreign completion and return the legitimate receipt.
2. Active thread, wrong turn: ignore the foreign completion and return the legitimate receipt.
3. Wrong thread and wrong turn: ignore the foreign completion and return the legitimate receipt.
4. Matching thread and turn: return the legitimate receipt.
5. Legacy absent thread identity, matching turn: return the legitimate receipt.
6. Foreign messages after the legitimate message: preserve every coordinator receipt field.
7. Malformed transport during the active phase: propagate failure and stop the fixture process.

The success cases also check that the fixture process stopped and its input closed. Cleanup runs the implementation's actual termination path against the simulated process; this is not a live provider or real OS process-group integration test. Candidate production files are evaluated through the existing sealed evaluator's clean-base reconstruction, immutable baseline tests, minimal environment and macOS filesystem/network sandbox. The new oracle runs seven selected cases, not the entire original regression suite.

## Controls and observed results

| Material | Verdict | Failed cases |
| --- | --- | --- |
| `base` | RED | wrong_thread_same_turn_cannot_finish_phase, same_thread_wrong_turn_cannot_finish_phase, wrong_thread_wrong_turn_cannot_finish_phase |
| `accepted-head` | GREEN | None |
| `tweed-pr32--original_cp_05--r1` | RED | same_thread_wrong_turn_cannot_finish_phase |
| `tweed-pr32--current_cp_06--r1` | GREEN | None |
| `tweed-pr32--compact_routing--r1` | RED | same_thread_wrong_turn_cannot_finish_phase |

The defective base fails the first three cases. The accepted head passes all seven. Original CP and compact routing both leave a genuine workflow failure: a completion for the coordinator thread but a different turn causes `run_phase` to raise `Codex app-server completed the wrong turn` before it can consume the legitimate final receipt. Their process cleanup and the other six cases pass. Current CP's alternate filter location passes the whole seven-case matrix. Its missing terminal receipt, unknown billed cost, and interrupted benchmark execution remain separate facts and are not repaired by this audit.

## Frozen identity and receipts

Source frozen at `2026-10-12T15:00:30.189413+00:00`; bundle sealed at `2026-10-12T15:01:01.405731+00:00`.

- [workflow_audit_oracle.py](workflow_audit_oracle.py), SHA-256 `ac0db6bfc98b52b4a9aeb06330de5af521880f41a26bd688ce28860f264bd141`.
- Sealed oracle-tree digest: `1fd76a2d71cadc99609b362fa8b3e8f779975ade54311cddd3bd913898da12e2` using the curation path/mode/file-digest algorithm.
- Existing sandbox evaluator SHA-256: `324b3d9eeb704584197ade4a69e0a5376fcc307e107c77f4c6b9997a035382aa`.
- Base commit `e6fa6128f73e28427b124cd361855b92307b0d5a`, source-tree digest `1fd87ae46bbc20f89b9c2b72bcd0f56efa24ee52e0c7c8bd1dc85b9f90d5675d`.
- Accepted head commit `2b84fec7f7ca6293747ba851f786557c999cb85d`, source-tree digest `830f7a2110fac48fa872696289dbd1faf60d7a283b2e1fe6356962bdc13c568a`.

| Material | Raw grader stdout SHA-256 | Submitted/result source digest (runner algorithm) |
| --- | --- | --- |
| `base` | `87a913e3820d611aa1570d8b7fb5d9d5e19eea77fe0f3266459d0c12af8f7f05` | `2e59722b4acf123136dfae4500c17a8189752819e2876380af7c62b33022d426` |
| `accepted-head` | `3904015d9174d6d0c971d6d74ac48654221c2f9fe223cbcfc2e49abef3ec8a26` | `973db08398a36f0b4a7be7d0702b0334fb1a1d052a1963b9f9158678b8668621` |
| `tweed-pr32--original_cp_05--r1` | `6aa2f23e78984b31d0729bcda3453e1ba7aa91c9b67a504b121ab67716f9ed29` | `d75cedd30e46991e6d61eeea178cc206754709e1143388afee836c86f4974ecf` |
| `tweed-pr32--current_cp_06--r1` | `3da665171d151e2eca9e55d2b5f7a218199abab2725de44c1d99c9331b2292ca` | `7251ba3f81881fdc57acfabc96c8829bff99d39b80a9819131e2413967ff6fe2` |
| `tweed-pr32--compact_routing--r1` | `dbd239afa99e9a53afa29af01471fb0d6b0ba0b134466d07416cd0b1f9f50945` | `3af0a0b713efef53f42a233d9df7e93576225924d787d45c4a89653a7d211fd6` |

Full registration, source/code hashes, raw stdout/stderr, per-material receipts and result inventory are retained under ignored `.confidence/benchmark/study/workflow-audit/`. The source file and this report are tracked separately from the original frozen benchmark materials. Any future cohort using this public-workflow oracle must independently freeze its task, input, oracle, model, budget and analysis rules before solver outcomes; this retrospective result supplies fairness evidence, not an excuse to rescore the existing cohort.

## Cohort-wide secondary audit and separate prospective selection

The unchanged secondary oracle is being applied to all 14 scheduled PR32 artifacts, including unfinished submissions, as they arrive. Its schedule is recorded separately before those additional secondary evaluations. Pending or integrity-invalid artifacts retain unknown secondary grades. The initial three submissions shown above explain the motivating discrepancy; they are not selected as an efficacy sample. The cohort-wide secondary receipts and progress are stored under `workflow-audit/all-14-*` and remain separate from primary results.

[hybrid-selection.json](hybrid-selection.json) is a **separate prospective input selection** for a later mixed-harness study. PR32's task requirements and prompt are identical to the original selection. Its seven public-workflow checks use this audit's unchanged source; a new bundle with the original task identity passes fresh base RED, accepted head GREEN, and alternate current-CP GREEN controls. The other five task dictionaries and oracle identities remain unchanged. The selection explicitly discloses that this adaptation followed original-cohort observations. It cannot be presented as a preplanned oracle for the original 84 trials.

Prospective PR32 oracle-tree digest: `6f38d7b5dc4c739761c518ca3aa09339674053e0fa6ff956b7de188d36222c0a`. The differently named retrospective bundle has a different configuration digest; both contain the same `workflow_audit_oracle.py` code and seven case IDs. The prospective bundle's frozen sandbox evaluator remains byte-identical to the original evaluator.

To recreate the public-workflow bundle after exporting the original pinned snapshots with `prepare.py`, copy the byte-pinned `oracle_runner.py` into a fresh sibling `oracle/evaluate.py`, place this audit source in `oracle/modules/test_workflow_audit.py`, and serialize the following object with `json.dumps(value, indent=2)`, followed by one newline, into `oracle.json` to reproduce the whitespace-sensitive bundle digest. The sibling `base/` must be the complete exported PR32 base snapshot. Invoke `python3 -B oracle/evaluate.py --workspace <candidate>` outside every solver sandbox; the evaluator constructs and confines its own grading child.

```json
{
  "task_id": "tweed-pr32",
  "test_ids": [
    "tests.test_workflow_audit.WorkflowRoutingAudit.test_wrong_thread_same_turn_cannot_finish_phase",
    "tests.test_workflow_audit.WorkflowRoutingAudit.test_same_thread_wrong_turn_cannot_finish_phase",
    "tests.test_workflow_audit.WorkflowRoutingAudit.test_wrong_thread_wrong_turn_cannot_finish_phase",
    "tests.test_workflow_audit.WorkflowRoutingAudit.test_matching_thread_turn_finishes_phase",
    "tests.test_workflow_audit.WorkflowRoutingAudit.test_legacy_absent_thread_matching_turn_finishes_phase",
    "tests.test_workflow_audit.WorkflowRoutingAudit.test_foreign_messages_cannot_replace_coordinator_receipt",
    "tests.test_workflow_audit.WorkflowRoutingAudit.test_malformed_active_transport_stops_process"
  ],
  "production_paths": ["bonaparte", "bonaparte_native.py"]
}
```


## Complete 14-artifact secondary inventory

All 14 scheduled PR32 artifacts have now been evaluated once using the unchanged audit source and bundle. The table reports selected primary-oracle and retrospective public-workflow verdicts separately; it does not rewrite primary source-scope/model validity rules or comparative scores. Repeats at the same PR are not independent tasks.

| Arm | Repeat | Frozen primary oracle | Retrospective workflow oracle | Secondary failed cases |
| --- | ---: | --- | --- | --- |
| `original_cp_05` | 1 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `current_cp_06` | 1 | RED | GREEN | None |
| `compact_routing` | 1 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `counterexample_first` | 1 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `dependency_slicing` | 1 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `independent_review` | 1 | RED | RED | wrong_thread_same_turn_cannot_finish_phase, same_thread_wrong_turn_cannot_finish_phase, wrong_thread_wrong_turn_cannot_finish_phase |
| `bounded_repair` | 1 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `compact_routing` | 2 | GREEN | GREEN | None |
| `current_cp_06` | 2 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `original_cp_05` | 2 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `bounded_repair` | 2 | GREEN | GREEN | None |
| `independent_review` | 2 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `dependency_slicing` | 2 | RED | RED | same_thread_wrong_turn_cannot_finish_phase |
| `counterexample_first` | 2 | GREEN | GREEN | None |
