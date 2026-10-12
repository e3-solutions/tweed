# Retrospective public CLI budget/resume audit

All seven available first-repeat PR40 artifacts pass eight independently executed public CLI, actual phase execution and checkpoint-persistence cases, while their frozen primary oracle verdicts are RED. Within these cases, the frozen failures impose internal representation choices that the task requirements do not prescribe. This finding does not prove correctness outside the audited behavior or repair absent solver terminal receipts and unknown costs.

This is **RETROSPECTIVE SECONDARY** evidence. The original PR40 primary results and the motivating parse/resume shortcut were already inspected. The final audit source and case matrix were frozen before evaluating any candidate with this audit, then applied unchanged to all available PR40 submissions. All 14 scheduled PR40 artifacts, including unfinished ones, are included as they arrive; pending grades stay unknown. Nothing is forwarded to solvers or substituted for original primary scores.

## Cases and controls

The audit invokes `main()` using the real `resume <token> <answer>` CLI, actual checkpoint read/write and leasing, actual `resume_checkpoint` and `run_phase`, and real native driver construction against a deterministic line-oriented app-server fixture. Only provider process creation and provider discovery are simulated; ordinary local Git subprocesses execute in the grading sandbox. No disabled constant, `parse()` return token, or private helper positional/keyword call shape is asserted.

1. Explicit `--no-soft-phase-budget` replaces a saved positive budget and persists null.
2. Explicit disabling retains an already disabled saved budget.
3. Resume without an override retains a disabled saved budget.
4. A positive numeric override replaces a disabled saved budget and persists the number.
5. Resume without an override retains a saved positive number.
6. Zero, negative, NaN, infinity and nonnumeric overrides fail before provider startup.
7. Mutually exclusive budget flags fail before provider startup.
8. `BONAPARTE_SOFT_PHASE_BUDGET=off` drives a real fresh phase to a needs-input receipt and persists a disabled checkpoint.

Successful phases preserve the coordinator receipt, resume the original native session when applicable, do not send budget steering before normal fixture completion, and stop the fixture process. The fixture completes without a simulated elapsed deadline; this audit alone does not establish long-wait steering behavior. Existing frozen direct-None/no-steering checks are distinct evidence and are not modified.

The defective base is RED and the accepted head is GREEN. Two fixture-control drafts were rejected before candidate secondary evaluation: a broad Popen mock incorrectly intercepted real Git, and a completed fresh phase was incorrectly assumed to require a question checkpoint. The final fixture mocks app-server Popen only and asks for input when persistence is required. Both rejected code bundles, control stdout and hashes remain in `rejected-fixture-v1/` and `rejected-fixture-v2/`.

## Initial paired verdicts

| PR40 first-repeat arm | Original selected oracle | Retrospective public CLI audit |
| --- | --- | --- |
| `current_cp_06` | RED | GREEN |
| `compact_routing` | RED | GREEN |
| `counterexample_first` | RED | GREEN |
| `dependency_slicing` | RED | GREEN |
| `independent_review` | RED | GREEN |
| `bounded_repair` | RED | GREEN |
| `original_cp_05` | RED | GREEN |

Six primary failures occur when a value obtained by parsing `--no-soft-phase-budget` for `scope` is passed directly into the internal resume helper. Several submissions legitimately parse non-resume disabled execution as `None` and explicit resume disabling as a separate sentinel. The public CLI chooses the proper representation for each command; the frozen shortcut does not. The seventh implementation uses an internal disabled string before materializing execution/persistence; a frozen mocked-helper assertion demands `None` at that earlier internal boundary. Actual CLI execution and durable null persistence pass this audit.

These findings cover a single task slice and arise from an adaptive audit. They are not preplanned comparative efficacy evidence, do not establish an advantage for one Confidence Protocol arm, and do not replace the original cohort's registered outcome definition. Any later cohort adopting public CLI checks must separately freeze the choice and disclose that it followed these observations.

## Frozen source and raw evidence

Final source frozen at `2026-10-12T15:18:27.213170+00:00`, bundle sealed at `2026-10-12T15:18:27.517335+00:00`.

- [budget_resume_audit_oracle.py](budget_resume_audit_oracle.py), SHA-256 `2b6bdda7402b35958cd762ced0c7271d26c70ccf898591f711974409ad4ca403`.
- Final oracle-tree digest `74d252b4729042b28db0443be48e7f46adf499e46409a07f6d0696902222dd0e` (curation path/mode/file-digest algorithm).
- Sealed evaluator SHA-256 `324b3d9eeb704584197ade4a69e0a5376fcc307e107c77f4c6b9997a035382aa`; existing grader code is unchanged.
- Base `80289b8e2bfc5bcbf025114983e7639c56c63fd9`, source-tree digest `214297cc438dd04400ff45d147856cae3321a2e3306c3f2405039460d8c37d81`.
- Accepted head `deab1ca6ece0622aeee5ee92e909386c57f5d2d5`, source-tree digest `261ecc1a87a151e382d351cac3301e66fd6790bd59b3b44373292649e9c805b3`.

| Material | Verdict | Raw grader stdout SHA-256 |
| --- | --- | --- |
| `base` | RED | `3bca6176a255c32439a3bef23a9bd47f0ce55db5e5bd5a8cdfc9dedbc3f28195` |
| `accepted-head` | GREEN | `2f4f442792e4770780ba34ffc9860107ca279e67233a730d615abf2420c5e72b` |
| `tweed-pr40--current_cp_06--r1` | GREEN | `8e484c981683a0c8e228bb7861a14bf701a666f5ff75a8881172df08105fe268` |
| `tweed-pr40--compact_routing--r1` | GREEN | `b0160fbd24c49dfab25e4f9267ae467d2a6bc843582c3ce81a476965440b1162` |
| `tweed-pr40--counterexample_first--r1` | GREEN | `e9f6d17ff36632f1e1aec75ccd663f2aa9ad0d6437ac5499a129c119aa3d1797` |
| `tweed-pr40--dependency_slicing--r1` | GREEN | `8e484c981683a0c8e228bb7861a14bf701a666f5ff75a8881172df08105fe268` |
| `tweed-pr40--independent_review--r1` | GREEN | `20e4348d9f5817515935fbfcd9af2c87b0a2c9b613124fe6e0a630e87fa5f0e0` |
| `tweed-pr40--bounded_repair--r1` | GREEN | `7e67ff5eb4426bfb1fc4fc0c06b5de13e69b76f2e62827078a70ae93fd6f532e` |
| `tweed-pr40--original_cp_05--r1` | GREEN | `7fe35c5d641b060e30f14040fcf9a5c3dd7d5fe252f025843692c78aa8de5ab3` |

Registration, all eight test IDs, raw stdout/stderr, per-material receipts, submitted-result source digests, and the complete 14-trial secondary schedule are retained in ignored `.confidence/benchmark/study/budget-resume-audit/`. Primary receipts and grading outputs remain untouched. Source, case IDs and sandbox evaluator identity supply a reproducible bundle: place the audit source at `oracle/modules/test_budget_resume_audit.py`, the byte-pinned evaluator at `oracle/evaluate.py`, and the complete pinned base at the sibling `base/`; serialize an `oracle.json` with task identity, the eight test IDs and production paths `bonaparte` and `bonaparte_checkpoint.py`. Run the evaluator outside solver contexts so it confines its own grading child.


## Separate prospective ninth case

A later prospective hybrid selection adds [budget_elapsed_audit_oracle.py](budget_elapsed_audit_oracle.py) without modifying the frozen eight-case secondary oracle. The actual resume CLI explicitly disables a previously saved 0.001-second budget. After the native turn-start acknowledgement, the provider fixture withholds its receipt for 0.05 real seconds, crossing the former budget. Actual `run_phase` must return the normal coordinator receipt, persist null, stop the process and issue no `turn/steer` command. It does not inspect parse tokens, disabled constants, intermediate helper arguments or a private filter location.

This checks waiting across the former stored deadline; it does not exhaust every possible hidden timer or exercise a live provider. The ninth source was frozen before these controls and before hybrid outcomes. Base RED, accepted head GREEN, and all seven already observed first-repeat alternate implementations GREEN controls passed all nine cases. Adoption is disclosed as an adaptive prospective change informed by the original cohort, rather than a preplanned original-cohort efficacy result.

- Ninth source frozen at `2026-10-12T15:23:32.227583+00:00`, SHA-256 `d6dd845d20f518f28ac5bdd6f4d4dac5fc7ef3583382e4797b10d5659956e3b2`.
- Unchanged eight-case source SHA-256 `2b6bdda7402b35958cd762ced0c7271d26c70ccf898591f711974409ad4ca403`.
- Prospective nine-case oracle-tree digest `2b7145ab3eda4698a5fa135db7a38a3eff47b7de0464be4e43093f54fc0c18ab`.
- [hybrid-selection.json](hybrid-selection.json) records the separate PR40 adaptation. PR32's earlier workflow oracle remains intact; the four other original task/oracle dictionaries remain unchanged. Every task requirement and prompt is unchanged.

| Nine-case control material | Verdict | Raw grader stdout SHA-256 |
| --- | --- | --- |
| `base` | RED | `aed0b4395d390a11dbf5a3ad919bf49156313890f020de27a3c65e22543a051c` |
| `accepted-head` | GREEN | `99efcb788f1362a251b570181d58136c0801be576b22891df04cb3eaf7ba429f` |
| `tweed-pr40--bounded_repair--r1` | GREEN | `5f863cf672f1feb6a00bef3b32a4a5e6e93926c20e195d7ebd94f7410d3b18a4` |
| `tweed-pr40--compact_routing--r1` | GREEN | `ed58fba879de5541d7e9f5fe42ac1e52dd0aea6f46376a6764ee2cea7fdc2147` |
| `tweed-pr40--counterexample_first--r1` | GREEN | `2cdb0ef768e84e28d07c5a1469131f3ea0a67c134da1592aea978e0a46b5cbaa` |
| `tweed-pr40--current_cp_06--r1` | GREEN | `bb9b811dbace1f29adb00712e72328c0045cf838f16c3c88fc3c0505caf8bbcb` |
| `tweed-pr40--dependency_slicing--r1` | GREEN | `c7c8055fac7ae1d10add8f13a00b25285de87f3336431892560648ceef83f2aa` |
| `tweed-pr40--independent_review--r1` | GREEN | `52d0b589415b151ca0a3b4d901e22f6c097ea6b8b8456c9e4f81c5b1e5401d24` |
| `tweed-pr40--original_cp_05--r1` | GREEN | `ca2be6e23bac821404d91b29be8fade8b4adc8ff58f7308b439829506cc8d717` |

All source, configuration, old selection versions and raw control receipts remain in `budget-resume-audit/prospective-nine/`. The original 84 primary results and unchanged all-14 eight-case secondary results are preserved separately.


## Complete 14-artifact secondary inventory

All 14 scheduled original PR40 artifacts have been evaluated once with the unchanged eight-case secondary source and bundle. Primary and secondary oracle verdicts are preserved separately; original source-scope/model validity rules and comparative scores are not rewritten. This complete inventory includes every scheduled arm and both repeats, rather than selecting successful artifacts. Repeats remain clustered at one PR.

| Arm | Repeat | Frozen primary oracle | Retrospective public CLI oracle | Secondary failed cases |
| --- | ---: | --- | --- | --- |
| `current_cp_06` | 1 | RED | GREEN | None |
| `compact_routing` | 1 | RED | GREEN | None |
| `counterexample_first` | 1 | RED | GREEN | None |
| `dependency_slicing` | 1 | RED | GREEN | None |
| `independent_review` | 1 | RED | GREEN | None |
| `bounded_repair` | 1 | RED | GREEN | None |
| `original_cp_05` | 1 | RED | GREEN | None |
| `counterexample_first` | 2 | RED | GREEN | None |
| `compact_routing` | 2 | RED | GREEN | None |
| `current_cp_06` | 2 | GREEN | GREEN | None |
| `original_cp_05` | 2 | GREEN | GREEN | None |
| `bounded_repair` | 2 | RED | GREEN | None |
| `independent_review` | 2 | RED | GREEN | None |
| `dependency_slicing` | 2 | RED | GREEN | None |
