# Evidence workflow

Use this reference when capturing Standard/Critical work. Resolve `scripts/confidence.py` relative to this skill. Use one task-specific evidence directory. Keep generated evidence untracked; tracked report edits change source identity. Reuse the working interpreter, Git context, and directory across commands. Relative `--directory` paths resolve from the caller's current directory, not the command's `--cwd`.

## Initialize and define proof

Set `CP` to the absolute script path. The examples run from the project root and assume its focused tests live under `tests`:

```sh
python3 "$CP" init --directory .confidence --title "Local behavior" --mode standard --task-type bug
```

`init` and `record` require Unix directory locking; unsupported platforms refuse. They coordinate cooperating writers through a shared advisory lock. Retry contention after the active writer finishes; manual editors are not serialized. Each document is published atomically, but the contract/report pair is not a transaction.

Initialization creates templates, not completed evidence. Fill `contract.json` before implementation. A minimal contract shape is:

```json
{
  "version": 1,
  "task": {"title": "Local behavior", "mode": "standard", "type": "bug"},
  "intent": {
    "goal": "Reject invalid input while preserving valid results.",
    "must_happen": ["Valid input returns the established result."],
    "must_not_happen": ["Invalid input is accepted."],
    "constraints": [], "non_goals": [], "open_questions": [], "assumptions": []
  },
  "proof_obligations": [{
    "id": "P1",
    "claim": "Valid input succeeds and invalid input is rejected.",
    "verification": "Run focused public-behavior tests for both outcomes."
  }]
}
```

Replace example claims with the actual task. Preserve the generated report format: version 3, matching task title/mode, outcome, changes, evidence, tests, simplicity, review, risks, rollback, and user decisions. `record` updates one obligation result; you still author the other sections.

## Capture, inspect, record

```sh
python3 "$CP" run --json --directory .confidence --cwd . --id focused-after -- python3 -B -m unittest discover -s tests -v
```

The Python example uses `-B` to avoid creating bytecode files during capture. Choose the project’s actual focused command and test root. In disposable snapshots, use local dependency copies if the test runner writes caches; a dependency symlink can write into the original project. Arguments after `--` are an executable and separate arguments; the runner does not invoke a shell. Await completion. `--json` returns a compact receipt with `id`, `exit_code`, `log`, `record`, and `workspace_binding`. Follow those paths rather than guessing filenames. Inspect the log for what actually ran. Full output remains local; JSON suppresses replay, not capture. The exit of a pipeline display command does not establish the tested command's result.

Default `--max-log-bytes` is a stopping threshold: a fast output burst can exceed it before the runner stops the command. It is not a hard storage cap and does not limit files the child creates.

An exit-zero receipt is necessary for supporting a pass, not sufficient. Assess coverage and source binding, then explicitly record the judgment:

```sh
python3 "$CP" record --directory .confidence --obligation P1 --status pass --details "Focused tests exercised both valid and invalid input." --run focused-after
```

Each invocation replaces the selected result's reference sets. Repeat `--run`, `--diagnostic-run`, or `--artifact` to retain multiple references; omitting an old reference removes it from this result, not from immutable capture history. Expected pre-fix failures belong in diagnostic references. Artifacts supplement proof; they do not replace the captured run required for pass, including research tasks.

`record` returns JSON success/errors, checks the selected result, and makes an atomic report replacement. It does not infer semantic pass or check whole-report completion. It uses the coordinated writer lock described above.

## Complete or retain partial evidence

| Field | Meaning |
| --- | --- |
| `evidence[].status` | `pass`, `partial`, `fail`, or `not_run`; describe actual relevance and limits |
| `tests.passed` | Checks that actually passed |
| `tests.failed` | Current unresolved test failures; retain historical expected failures in diagnostics |
| `tests.not_run` | Required checks still missing |
| `risks` | Uncertainty and optional/out-of-scope checks with reasons; never hide a required gap here |
| `simplicity` | Explicit code/test gate judgment and rationale, not automatic results |
| `review` | Required flag/reason, actual roles and attributable findings; Critical requires `test_designer` and `adversarial_reviewer` |
| `rollback` | Practical undo path, or `Not applicable` when accurate |

Use exact `review.roles` values, not descriptive labels. Critical reports require `review.required: true` and both `"test_designer"` and `"adversarial_reviewer"`. Other accepted roles are `"critic"`, `"integration_reviewer"`, `"domain_reviewer"`, and `"security_reviewer"`. Put descriptive scope and attributable findings in the other review fields; valid role names do not establish that review happened.

When required proof is missing, record partial status with the gap:

```sh
python3 "$CP" record --directory .confidence --obligation P1 --status partial --details "Local checks passed; required database behavior remains unverified." --run focused-after
python3 "$CP" validate --directory .confidence && python3 "$CP" render --directory .confidence --force
```

Ordinary validation checks document/reference consistency. Successful validation and rendered reports identify recorded working directories, source roots, binding kinds, run IDs, and start/end observations. These are the captured locations, not the caller’s current checkout: copying evidence does not certify another checkout. Verify the displayed scope matches the claim; recapture in the intended checkout when it does not. A valid partial report is useful and does not establish completion. Once all required proof, report fields, simplicity gates, and required review are satisfied:

Before claiming completion, apply [report rules](report-rules.md), including that no open risk violates a must-not-happen condition.

```sh
python3 "$CP" validate --directory .confidence --require-complete && python3 "$CP" render --directory .confidence --force
```

The success-dependent sequence prevents rendering after a failed gate. `render --force` replaces an owned generated Markdown report; it does not strengthen evidence. CLI checks cannot establish that a claimed review occurred or that selected tests prove the intended behavior.

## Source binding and recovery

Current proof uses `git-content-v1`: Git-enumerated working-tree names, actual bytes/modes, symlink target strings, and missing tracked files. A supporting software pass requires matching source before/after capture and at validation. For stale evidence, rerun the original verification on the current tree, then record its new ID. Do not rewrite historical records or replace verification with a no-op to obtain fresh binding. Legacy `git` binding is readable but requires recapture for current software proof.

Unknown binding remains inspectable as partial evidence. Unsupported contexts include non-Git workspaces, gitlinks/submodules, conflicts, unsupported file types, repository/index/object routing environment overrides, and explicit `core.worktree` routing. Conventional linked worktrees are supported. Restore a supported context only when that preserves the task's execution meaning, then recapture; otherwise state the limitation. Research command observations can pass without claiming current software verification.

Reserve the evidence directory's generated-output names for protocol use. Untracked regular report/run outputs and exact atomic staging names (`.contract.json.tmp-<suffix>`, `.report.json.tmp-<suffix>`, `.REPORT.md.tmp-<suffix>`, `runs/.<run-id>.json.tmp-<suffix>`, with an eight-character lowercase/digit/underscore suffix) are excluded by name, not authenticated writer identity. Do not place source inputs there. Tracked files remain bound, including staging-looking names.

Ignored untracked inputs, untracked special files Git omits (such as FIFOs), external dependencies/services, and external symlink referents are outside the inventory. If a claim depends on those inputs, verify that boundary separately or retain partial proof. Stable observations do not prove an immutable snapshot: transient change-and-restore and changes after the final observation remain limits. File-generating checks may need another capture after their final source changes.

During active capture, SIGINT/SIGTERM cancellation retains the first signal status (130/143) and stops the captured process group. Interruption before publication begins leaves no completed record or receipt. Once publication or receipt delivery starts, interruption can leave a completed record or receipt; inspect the run files before retrying and use a fresh ID when recapturing. During log/child acquisition the runner defers interruption until it can clean up owned resources. This does not cover SIGKILL or power loss.

A runner or persistence failure exits 125 without a success receipt. Failure before record publication leaves no new record; final publication can succeed before a later persistence step fails, so inspect the record and log paths before deciding what exists. After fixing storage access or capacity, capture again with a fresh ID; never assume that retrying the same ID is safe. A child can also exit 125, in which case its completed capture exists. For a reused ID, inspect and reuse the old record only if it is the intended current observation, or omit `--id` to generate a new one. Never attribute an old record to a failed new attempt. The receipt/record preserves signed child status; a shell can encode a negative signal status differently. Use equivalent installed commands for bounded runtime recovery, recording what actually ran. Keep completed failed captures diagnostic; describe runner failures without inventing a missing record.

For missing documents, check `--directory` first. Initialize only a new task's intended directory. If interruption left only its intended `contract.json`, inspect that contract and resume:

```sh
python3 "$CP" init --directory .confidence --resume
```

Resume preserves every existing contract byte, derives task identity and obligation IDs from it, and creates a missing report with unfinished results. Matching complete pairs stay unchanged. Conflicting explicit identity, report-only state, malformed retained identity/IDs, or mismatched pairs are refused; inspect and retain those artifacts instead of guessing a repair. Resume is not full evidence validation.

`init --force` explicitly discards the old report before replacing the contract and creating a fresh report. It is not preserving recovery. Interruption may leave contract-only state, recoverable with `--resume` after inspecting identity; if no contract exists, initialize normally. There is no pairwise transaction or power-loss durability promise. If completion fails because required proof is partial, plain validation can check structure, but the missing proof remains required.

For tool failures, inspect `doctor` component results; copied-package metadata failures do not justify changing global installation state. Use `support-bundle` for redacted diagnostics. Never put secrets in argv, and inspect logs before sharing; local hashes detect drift, not forgery by a writer controlling both log and record.
