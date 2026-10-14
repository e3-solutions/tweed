# Evidence reconstruction and local replay limits

The public files retain the as-executed helper, task/evaluator specifications, source commits, original candidates, typed provider/tool evidence and current source/patch/grade bindings. The raw provider stream is private because it includes thinking; its digest is retained. Published provider-events.json contains initialization, actual tool-use/result and terminal/model/usage facts without thinking or assistant narrative. Reconstructing inputs or reading receipts requires no inference. This is not a portable one-command benchmark: the original paths, macOS sandbox, Python/CLI versions, existing adapter dependencies and runtime seals are host-specific.

From this repository, with the listed historical Git objects already available, reconstruct and verify the task/policy inputs in a fresh directory:

```sh
python3 -B docs/research/2026-10-confidence/fork-flush/reconstruct_inputs.py --output .confidence/fork-flush-reconstructed-inputs
```

The helper exports each pinned original base/head using the historical archive policy, restores PR45's export-ignored original tests directly from its Git objects, and verifies TASKS tree hashes. It projects only declared production files into the focused reference. It reconstructs all common references/toolkit from4758787, checks INCUMBENT file hashes, and overlays the unchanged published branch entrypoints. Missing objects or mismatching bytes fail; it does not fetch, change a study, or launch models. The retained INPUT-RECONSTRUCTION.json records an actually executed successful reconstruction of all six source-tree hashes and the incumbent/candidate input pins. This is input-byte evidence only, not a rerun of product behavior.

For an as-executed host-local replay, inspect the frozen public TASK-RUN-CONFIG.json, REGISTRATION.json and TASK-REGISTRATION.json first. Copy the frozen public helper/spec files to the original `.confidence/fork-flush/` layout, reconstruct the verified base/head/policy inputs at its registered paths, and retain the shared existing `pr-benchmark` and `claude-first-evaluation` dependencies at their recorded hashes. The original design outputs are in `designs/`; rerunning their authors is a different stochastic experiment. On another host or at different paths, create a separate registration and report it as a new replay rather than claim the original seals verify unchanged.

The original selection was prepared with:

```sh
python3 -B .confidence/fork-flush/run_tasks.py prepare --config .confidence/fork-flush/TASK-RUN-CONFIG.json --study .confidence/fork-flush/selection
```

That registered helper also writes the global RUNTIME-PREFLIGHT.json during prepare. In this experiment it overwrote the previously pinned global receipt. Before any task inference the team restored the exact original global bytes and original helper; the per-study prepared receipt and both registrations remained unchanged. The proposed one-line helper change was archived but NEVER used. A replay using this original helper must likewise preserve the global receipt before prepare, restore its exact registered bytes after prepare, and verify both root/study seals before dispatch. Do not overwrite or reprepare an existing study. The relevant exact files and hashes are in `setup-handling/AMENDMENT.json` and `RESTORATION-VERIFIED.json`.

On the original layout, the source-preserving restoration was equivalent to:

```sh
cp docs/research/2026-10-confidence/fork-flush/setup-handling/driver.before.py .confidence/fork-flush/run_tasks.py
cp docs/research/2026-10-confidence/fork-flush/setup-handling/global.original-public-precommit.json .confidence/fork-flush/RUNTIME-PREFLIGHT.json
python3 -B .confidence/fork-flush/verify_seal.py
```

Task stage commands were `run_tasks.py solve --study ... --cell <registered-cell-id>` and, only after an observed required gap and a bound safe feedback packet, `run_tasks.py repair --study ... --cell <registered-cell-id> --feedback <packet>`. Each independently grades a frozen source projection. Actual calls require fresh explicit dispatch authorization and incur cost; these instructions are evidence, not authorization to rerun them. Confirmation was not run because both candidates failed static eligibility. Preserve the two-cell concurrency cap globally across main and repair stages; the recorded selection violated it when a repair overlapped two active mains, so its outcomes remain behavior diagnostics with a controller-fidelity limitation.

Inspect saved evidence without rerunning models or passing product checks using:

```sh
python3 -B docs/research/2026-10-confidence/fork-flush/export_evidence.py --final
```

This command requires the retained private original stream/source snapshots to rederive and bind the public export. Public-only consumers can verify ARTIFACTS.json hashes and inspect typed facts, commands, patches, scope diffs and owner logs; they cannot reconstruct discarded thinking from a hash. PRE-INFERENCE-ARTIFACTS.json is retained unchanged; the final manifest excludes itself.
