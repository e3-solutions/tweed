# Bonaparte

Bonaparte takes one software request from a human-readable Linear issue to a
reviewed, ready-for-review GitHub pull request. Each phase starts a fresh local
Codex task; Linear is the durable handoff, and the invoking task sees only a
bounded JSON receipt.

Before each non-create phase, the runner deterministically fetches Linear and
passes only the latest phase-specific handoff: intake to RCA, RCA or feature
intake to scope, scope to implementation, implementation to review, and review
to publish. The issue's official `gitBranchName` is preserved as metadata for
implementation.

```text
Bug:     create → RCA → scope → implement → review → publish
Feature: create → scope → implement → review → publish
```

Every phase after creation receives only the Linear issue identifier. Its fresh
coordinator reads the issue description and completed Bonaparte comments, performs
bounded internal work, and writes one self-contained evidence-bearing comment
before it can complete. Coordinator and subagent conversations are never
transferred between phases, and there are no hidden report files or local state
channels. The JSON receipt stays below 4 KiB and carries control state and
provenance only. Resuming the same coordinator after `needs-input` is the sole
within-phase context exception.

The durable comments intentionally retain the material information needed by
the next phase: causal and repository evidence, affected files and boundaries,
decisions and objections, confidence and unresolved gaps, ordered work,
validation, Git provenance, review dispositions, and final delivery state. Raw
subagent transcripts and tool logs are never published.

## Install

Bonaparte uses your local Codex installation and its authenticated Linear MCP. The
implement, review, and publish phases also use your existing Git and GitHub CLI
authentication.
Bonaparte does not pin a model. With no Bonaparte model setting, coordinators and
subagents use your normal Codex configuration. Bonaparte keeps reasoning effort at
medium for both.

Prerequisites:

- macOS or Linux with Git and Python 3.10+
- a working local `codex` command
- the GitHub CLI (`gh`) for draft and published pull requests

Copy and run this installer:

```sh
#!/bin/sh
set -eu
checkout=$(mktemp -d)
trap 'rm -rf "$checkout"' 0
git clone -q https://github.com/e3-solutions/tweed.git "$checkout"
"$checkout/install"
```

The temporary checkout is removed after installation. The installer copies
committed `HEAD` into a versioned snapshot under
`~/.local/share/bonaparte/releases/`. Three stable links select that snapshot:

- `~/.local/bin/bonaparte` → the active release's launcher
- `~/.local/bin/autoresearch` → the active release's standalone research runner
- `~/.codex/skills/use-bonaparte` → the active release's Codex skill

The checkout can then move between branches or be deleted without changing the
installed behavior. If `~/.local/bin` is not already on `PATH`, add it to your
shell configuration:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Connect the local Codex installation to Linear and authenticate GitHub:

```sh
codex --version
codex mcp add linear --url https://mcp.linear.app/mcp
codex mcp login linear
gh auth login
```

If those integrations are already configured, the add/login commands can be
skipped. Verify the installation without creating external work:

```sh
bonaparte --help
autoresearch --help
codex mcp list
gh auth status
```

For a non-default location, set `BONAPARTE_BIN_DIR`, `BONAPARTE_HOME`, or `CODEX_HOME`
when running `./install`.

## Status and updates

Inspect the exact installed release identifier and the highest published stable
`vX.Y.Z` tag without changing the installation:

```sh
bonaparte status
```

The command prints exactly `installed: IDENTIFIER`, `latest: vX.Y.Z`, and
`current: yes|no`. If the repository is unavailable, it preserves the installed
line, prints `latest: unavailable` and `current: unknown`, and exits nonzero.

At most once per 24 hours, an ordinary Bonaparte invocation makes the same
bounded stable-tag check. When a newer release exists it prints one concise
alert directing you to the update command. It remains silent when current or
offline and never fetches, validates, or switches a release automatically.
Set `BONAPARTE_AUTO_UPDATE=0` to disable this check while retaining explicit
status and update commands.

Only this explicit command installs an update:

```sh
bonaparte update
```

The updater fetches the advertised Git object for the highest stable tag into a
unique staging directory, verifies that the tag did not move, validates the
complete bundle and both CLI smoke tests, and commits the release with one
atomic switch of the shared `current` symlink. The bundle contains the launcher,
phase runner and runtime modules, every workflow (including autoresearch
workflows), the `use-bonaparte` skill, and the `autoresearch` companion command.
All managed consumers resolve through that one release.

An installation from exact legacy release
`local-v0.3.0-8b75b707dce8` needs only one `bonaparte update` command. Its old
launcher switches the complete bundle; the first subsequent invocation of the
new launcher safely materializes the previously absent autoresearch link. Verify
the result with:

```sh
bonaparte --help
autoresearch --help
```

The migration replaces only a missing link or an existing symlink. It refuses
and preserves a non-symlink at any managed CLI or skill target path. Validation,
network, interruption, or competing-update failure leaves either the old complete
release or the new complete release active. Retry `bonaparte update` after fixing
the reported cause; versioned releases are retained, so recovery never requires
deleting the current snapshot. Run `./bonaparte` directly when developing against
a live checkout.

Maintainers publish an update only after the reviewed commit's archived bundle
passes the manifest and CLI smoke checks. Push one new immutable stable tag such
as `v0.4.0`, verify that it resolves to that reviewed commit, then verify status
and the legacy upgrade canary. Protect `v*` tags from modification. Roll back by
publishing a higher corrective stable tag and directing users to
`bonaparte update`; never move or delete a published tag. No release archive or
package registry is required.

## Standalone autoresearch

`autoresearch` runs a bounded, local experiment loop before implementation. It
is independent of the Bonaparte phase runner: it does not create or update a
Linear issue, read or write GitHub, invoke a Bonaparte phase, apply its winning
patch to the source repository, commit, or push.

Start by generating a v1 research specification for a repository and goal:

```sh
autoresearch setup \
  --repo /absolute/path/to/project \
  --output /absolute/path/to/research/setup \
  "Reduce the parser benchmark without changing accepted syntax"
```

Setup writes `spec.json` and its schema in the output directory. Review the spec
before running it, especially every path, budget, evaluator argv array, and
sandbox wrapper argv. Those arrays are the execution authority: autoresearch
invokes the reviewed entries directly, without treating them as shell text or
allowing a worker to substitute another evaluator. A v1 spec has this shape:

```json
{
  "schema_version": 1,
  "goal": "Reduce the parser benchmark without changing accepted syntax",
  "repository": {
    "path": "/absolute/path/to/project",
    "source_oid": "1111111111111111111111111111111111111111",
    "baseline_oid": "1111111111111111111111111111111111111111"
  },
  "paths": {
    "allowed": ["src/parser"],
    "protected": ["tests/fixtures"]
  },
  "evaluator": {
    "argv": ["python", "benchmarks/parser.py", "--json"],
    "baseline_argv": ["python", "benchmarks/parser.py", "--json", "--baseline"],
    "check_argv": ["python", "benchmarks/parser_check.py", "--json"],
    "constraint_names": ["tests_pass", "accepted_syntax_unchanged"],
    "immutable_inputs": ["tests/fixtures"],
    "direction": "max",
    "timeout_seconds": 60,
    "max_output_bytes": 65536
  },
  "sandbox": {
    "wrapper_argv": ["approved-sandbox", "--network=none", "--"],
    "capabilities": [
      "filesystem-contained",
      "process-contained",
      "network-denied"
    ]
  },
  "budgets": {
    "attempts": 12,
    "concurrency": 3,
    "wall_seconds": 3600,
    "process_seconds": 300,
    "artifact_bytes": 104857600
  },
  "search": {
    "directions": ["allocation", "tokenization"],
    "adversarial_direction": "try to falsify the current best",
    "target": 0.9,
    "patience": 4,
    "min_improvement": 0.01
  },
  "provenance": {
    "created_by": "autoresearch setup",
    "created_at": "2026-08-08T12:00:00+00:00"
  }
}
```

After reviewing the spec, start a run and choose the directory that will hold
its durable state:

```sh
autoresearch run /absolute/path/to/research/setup/spec.json \
  --state /absolute/path/to/research/run-001
```

The baseline command (`baseline_argv`), candidate command (`argv`), and
independent check (`check_argv`) must each print exactly one JSON object
containing a finite numeric `metric` and the boolean keys declared by
`constraint_names`—no missing, extra, or non-boolean constraints. The applicable
primary result (baseline or candidate) and independent check must be identical.
For example:

```json
{
  "metric": 0.84,
  "constraints": {
    "tests_pass": true,
    "accepted_syntax_unchanged": true
  }
}
```

Every `immutable_inputs` path must sit under a protected path. Before each
evaluation, autoresearch replaces those paths with baseline-owned copies and
rejects the evaluation if their content changes. This keeps fixtures and other
objective inputs outside worker and evaluator authority.

Attempts execute in deterministic, bounded batches of at most `concurrency`.
Every member of a batch starts from the same promoted parent; direction
allocation and the final adversarial search slot are deterministic. Completion
timing does not decide the winner: verified records are ordered by attempt ID,
ranked by metric with a stable attempt-ID tie-break, and promoted serially.
Attempts, wall time, per-process time, captured output, and artifact bytes all
remain subject to the reviewed budgets.

Each state directory is one run. It pins a copy of the reviewed spec and keeps
its schemas, candidate and final patches, knowledge, and result together. Its
numbered event records are append-only and hash-chained. Checkpoint and result
files are caches, never resume authority. `run` refuses to replace existing run
state; use a new directory for a new run. If a process stops, `resume`
reconstructs decisions from the event log, verifies referenced patch digests,
freshly replays the pinned baseline evaluation, and marks incomplete leases
abandoned instead of restoring model sessions:

```text
run-001/
├── spec.json
├── checkpoint.json
├── events/
├── evidence/
│   ├── 00000001.patch
│   └── final.patch
├── schemas/
├── knowledge.json
└── result.json
```

```sh
autoresearch resume /absolute/path/to/research/run-001
```

The final result is bounded so it can be inspected and handed to a later,
explicit Bonaparte request without loading the whole experiment history. Before
writing it, autoresearch reconstructs the winning tree from the pinned baseline
and patch, performs a fresh objective evaluation including the independent
check and immutable-input verification, and requires a fresh bound critic to
raise no supported objection. For example:

```json
{
  "schema_version": 1,
  "run_id": "0123456789abcdef0123456789abcdef",
  "status": "completed",
  "baseline_metric": 0.71,
  "best_metric": 0.84,
  "best_attempt_id": 7,
  "baseline_oid": "1111111111111111111111111111111111111111",
  "best_tree": "2222222222222222222222222222222222222222",
  "patch": "/absolute/path/to/research/run-001/evidence/final.patch",
  "patch_digest": "3333333333333333333333333333333333333333333333333333333333333333",
  "evidence": "/absolute/path/to/research/run-001/events",
  "knowledge": "/absolute/path/to/research/run-001/knowledge.json"
}
```

Treat repository code, generated patches, tool output, and model-written notes
as untrusted input. Run only specifications whose repository, output/state
directories, and argv entries you have reviewed. Capability labels document the
required boundary; the reviewed wrapper is what must actually enforce it. Use a
real OS-level sandbox or disposable environment, including network denial, for
untrusted evaluation. The source repository must be clean and pinned, remains
unchanged, and must not contain the setup or run directories.

Autoresearch produces a candidate `evidence/final.patch`, compact event
evidence, and reusable `knowledge.json`. A human can review that bounded result
and explicitly hand it to a later Bonaparte request. Autoresearch itself does
not apply the patch or start an implementation, review, or publish phase, and
grants no authority to mutate the source checkout or external systems.

## Commands

```sh
bonaparte create bug "problem given by user"
bonaparte create feature "capability requested by user"
bonaparte RCA LIN-123
bonaparte scope LIN-123
bonaparte implement LIN-123
bonaparte review LIN-123
bonaparte publish LIN-123
bonaparte resume <resume-token> "clarification answer"
bonaparte inspect <phase-token>
```

Each coordinator turn has a soft, cooperative time budget. The default is 300
seconds; select a positive, finite number of seconds for one fresh or resumed
turn with `--soft-phase-budget-seconds`:

```sh
bonaparte --soft-phase-budget-seconds 600 implement LIN-123
bonaparte --soft-phase-budget-seconds 120 resume <resume-token> "Continue"
```

The budget starts fresh for each coordinator turn. On expiry Bonaparte persists
`finalizing`, sends at most one native steer, and waits for a bounded finalization
window (`--finalization-window-seconds`, default 30). Settled work may return a
receipt; otherwise Bonaparte attempts native interruption and records a
failed-resumable result requiring reconciliation. A steering acknowledgement is
not a quiescence guarantee. Unsupported, rejected, delayed, or unobservable
capabilities are reported explicitly. The finalization window must be positive,
finite, and no greater than 300 seconds.

## Model selection

Select a model for one phase or for a resumed phase with `--model`:

```sh
bonaparte --model gpt-5.6-terra scope LIN-123
bonaparte --model gpt-5.6-luna resume <resume-token> "clarification answer"
```

Set one model for every Bonaparte phase in the environment:

```sh
export BONAPARTE_MODEL=gpt-5.6-terra
```

Precedence is `--model`, then `BONAPARTE_MODEL`, then Codex's configured model.
An explicit selection applies to the phase coordinator and all of its subagents.

- **Create** writes a human title and a `What`/`Why`/`How` description for a bug
  or feature. It adds no comment.
- **RCA** delegates independent reproduction, tracing, and falsification work,
  then writes the first Bonaparte comment.
- **Scope** turns an established bug cause or feature outcome into the smallest
  implementation-ready plan after independent reuse, simplicity, and
  robustness analysis.
- **Implement** creates or reuses the official Linear branch and one draft PR,
  then pushes each coherent, verified implementation commit to that draft.
- **Review** independently challenges the complete diff, applies only verified
  in-scope corrections, pushes any correction commits to the same draft, and
  records the final commit.
- **Publish** verifies and finalizes that draft, marks it ready for review, and
  records its URL in Linear. It never merges or deploys.

When a user asks an agent to use Bonaparte, the skill selects the bug or feature
route, runs the commands in sequence, and passes only the Linear issue identifier
between them. Any `needs-input`, `blocked`, or failed phase stops the chain.
After `needs-input`, `resume` continues the same coordinator session with the
answer instead of restarting its investigation. The opaque `resume_token` is
stable across follow-up questions; the older
`resume <phase> <session-id> <answer>` form remains accepted for compatibility.
Soft-budget expiry produces `needs-input` with an exact instruction to resume
the token with `Continue`; other `needs-input` receipts contain one material
clarification question. Relay that exact question to the user, then pass the
user's answer back with the same token so the exact native thread resumes.

## Durable clarification checkpoints

A `needs-input` receipt includes a `resume_token` backed by a private checkpoint
under `$BONAPARTE_HOME/checkpoints` (normally
`~/.local/share/bonaparte/checkpoints`). The checkpoint records the native Codex
session, worktree and branch, changed-file and completed-check inventories,
current activity and blocker, and whether remote changes are known. The native
Codex session remains the source of truth for coordinator and subagent history;
Bonaparte does not copy their transcript.

Before resuming, Bonaparte exclusively locks the token and durably records the
answer. A later question reuses the same token. Completed and blocked records
remain on disk as authoritative receipts; repeated resume returns the committed
receipt without rerunning. Only `waiting-input` and `failed-resumable` records
may resume. If native delivery becomes
ambiguous, Bonaparte preserves the pending answer and reports the token instead
of silently restarting the phase. Token resumes reuse the saved model and
reasoning unless an explicit override is supplied. They also reuse the saved
soft phase budget unless `--soft-phase-budget-seconds` explicitly overrides it
for that resumed turn.

Every phase allocates a durable phase token before native coordinator work.
Native thread and turn identifiers are atomically committed as soon as the
provider returns them. A schema- and privacy-validated receipt is committed as
the authoritative terminal record before control returns from the native turn,
so a later host-process crash does not discard already-observed authority.
Receipt protocol v2 adds `phase_token`, `reason_code`, `user_action_required`,
`input_kind`, `safe_to_resume`, `reconciliation_required`, `remote_state`,
`runtime_version`, `receipt_protocol`, and `progress_abi`; the older
`remote_state_changed` boolean remains as a compatibility projection.
`bonaparte inspect <phase-token>` performs read-only Git, exact PR, and Linear
phase-artifact observations and never persists or writes. Resume repeats this
reconciliation immediately before answer delivery and fails closed on a changed
or unknown observation. Create recovery is stricter: after receipt loss, only one
issue carrying the exact durable phase-token marker and passing provider readback
is authoritative; missing or ambiguous correlation requires reconciliation, and
a title or fuzzy search is never proof that creation occurred. The legacy three-argument resume
form requires an existing checkpoint whose token and phase match exactly and
never creates a fresh run.

Receipt and checkpoint serialization is privacy fail-closed. Control text,
authorization headers, secret-like tokens, private keys, direct email contacts,
and local/private HTTP endpoints are rejected instead of persisted or emitted.
The fixed semantic progress vocabulary, opaque identifiers, canonical provider
URLs, and local recovery metadata remain supported. Rejected text produces a
bounded failure receipt without echoing the rejected value.

Stable update availability is advisory and never changes an active phase's
runtime. An explicit update affects only the next process. After updating, stop
the phase chain and reload the installed skill before starting another phase;
in-memory Codex skill-cache invalidation is upstream and is not claimed here.

## Semantic progress for trusted hosts

Every fresh or resumed create, RCA, scope, implement, review, and publish run
has an optional, host-controlled progress channel. Before launching Bonaparte,
a trusted host may open a writable file descriptor numbered 3 or higher,
configure it as nonblocking, explicitly inherit it into the launcher, and set
`BONAPARTE_PROGRESS_FD` to that descriptor number. The launcher preserves the
descriptor when it replaces itself with the final runner. Update subprocesses
do not inherit the descriptor or its environment variable. No other transport
or progress setting exists.

The channel is UTF-8 JSON Lines using progress ABI version 3. Each record has
`version`, `progress_abi`, `sequence`, `phase`, `state`, `elapsed_seconds`,
`runtime_version`, `update_state`, and `semantic`. Both `version` and
`progress_abi` are exactly `3`; `sequence` is a strictly increasing integer for
one process; `phase` is one of `create`, `rca`, `scope`, `implement`, `review`,
or `publish`; and `elapsed_seconds` is a nonnegative monotonic duration rounded
to milliseconds. A resume starts a new process sequence and elapsed clock while
restoring only its safe durable semantic snapshot.

`state` is one of `started`, `update-available`, `active`, `finalizing`,
`completed`, `needs-input`, `blocked`, `failed`, or `interrupted`.
`update-available` is advisory and may follow `started`; it does not change the
active runtime. `semantic` is the latest snapshot plus
its bounded `milestones` list:

```json
{"version":3,"sequence":7,"phase":"implement","state":"active","elapsed_seconds":30.004,"runtime_version":"v0.4.0","update_state":"current","semantic":{"stage":"checking","actor":"subagent-1","activity":"check","status":"completed","count":3,"milestones":[],"milestones_total_count":0,"milestones_truncated":false}}
```

The snapshot and every milestone have exactly five typed fields: `stage`,
`actor`, `activity`, `status`, and `count`. Their allowed values are:

| Field | Allowed values |
|---|---|
| `stage` | `coordinating`, `searching`, `tool-use`, `checking`, `file-changes`, `subagent-assignment`, `subagent-completion`, `waiting-input`, `finalizing`, `terminal` |
| `actor` | `null`, `coordinator`, or an opaque per-run ordinal `subagent-N` where `N` is from 1 through 32; overflow is coalesced into ordinal 32 |
| `activity` | `null`, `lifecycle`, `search`, `tool`, `check`, `file-change`, `subagent` |
| `status` | `null`, `started`, `in-progress`, `completed`, `failed`, `waiting`, `interrupted` |
| `count` | `null` or an integer from 0 through 2147483647; when present, the generic cumulative count for the current activity |

When milestones exist, `semantic` also contains `milestones`,
`milestones_total_count`, and `milestones_truncated`. The total is a
nonnegative integer no smaller than the retained list length, and the boolean
truncation flag reports whether earlier milestones were omitted. These three
fields are absent before the first milestone. Milestone totals and all activity
counts saturate at 2147483647. One native event fans out to at most 32
deduplicated actors.

Bonaparte continuously drains native Codex JSONL but translates only recognized
structural event types and typed fields into this fixed taxonomy. Events within
one heartbeat window update the latest snapshot; Bonaparte does not write one
progress line per native event. Milestones are same-shaped, deduplicated, and
capped at 32. The oldest milestones are also removed when necessary to keep the
entire progress record at or below 4 KiB. Unknown, malformed, oversized, or
string-bearing native event data is drained and ignored.

Emission is best effort. `started` is immediate; `active` is a heartbeat every
10 seconds and repeats the latest compact semantic state even when no new native
event arrives; and `finalizing` is emitted immediately after heartbeat shutdown
and join. Exactly one terminal event follows the flushed stdout receipt and
matches that validated receipt. Sequences remain increasing and elapsed time
remains monotonic across heartbeat and event-update races.

The channel never forwards or stores raw JSONL, logs, commands, output, file
contents or paths, patches, prompts, queries, arguments, URLs, messages,
reasoning, transcripts, task text, arbitrary model text, secrets, PII, or issue
or customer data. Structural identifiers are represented only by the local
opaque actor ordinals. Clarification checkpoints persist the latest safe
snapshot, at most 32 milestones, and bounded count/truncation metadata alongside
the existing private question state; they are not event logs. Existing version
1 and version 2 checkpoints remain readable. They normalize missing semantic
state as needed and the missing budget to 300 seconds before a subsequent
version 3 write.

Soft phase budgets do not change this progress ABI or its privacy boundary.
Progress remains advisory and does not become a deadline, cancellation, or
coordinator-content channel.

The host-supplied descriptor must already be nonblocking; Bonaparte rejects a
blocking descriptor without changing its blocking mode. An invalid, closed,
full, or partially writable descriptor, or any encoding, size, or write error,
permanently disables progress for that process. Bonaparte does not retry and
never falls back to stdout, stderr, a file, or a service. There is no watchdog,
timeout, or cancellation behavior associated with progress.

Progress ABI version 3 is intentionally incompatible with earlier records.
Hosts must negotiate ABI 3 before enabling the
channel. Regardless of progress availability, stdout remains exactly one final
JSON receipt of at most 4 KiB and stderr remains the diagnostic channel.
Progress is advisory: it does not establish phase success or replace the final
receipt.

## Runtime layout

The executable runner owns phase orchestration only. Supporting boundaries stay
in small importable modules:

- `bonaparte_native.py` owns Codex app-server transport and process groups.
- `bonaparte_progress.py` owns progress records and native event normalization.
- `bonaparte_linear.py` reads deterministic Linear intake through that transport.
- `bonaparte_checkpoint.py` validates and atomically stores resumable questions.

Tests mirror those boundaries. Current native protocol examples live under
`tests/fixtures`; update the fixture and its focused tests together when Codex's
event ABI changes.
