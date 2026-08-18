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
`~/.local/share/bonaparte/releases/`. Two stable links select that snapshot:

- `~/.local/bin/bonaparte` → the active release's launcher
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
codex mcp list
gh auth status
```

For a non-default location, set `BONAPARTE_BIN_DIR`, `BONAPARTE_HOME`, or `CODEX_HOME`
when running `./install`.

## Updates

At most once per day, Bonaparte checks the public repository for the highest stable
`vX.Y.Z` tag. It fetches that exact Git ref into a new directory and smoke-tests
it before switching the active release atomically. A failed check never prevents
the installed runtime from starting.

```sh
bonaparte update
```

Set `BONAPARTE_AUTO_UPDATE=0` to disable the daily check. Run `./bonaparte` directly
when developing against a live checkout.

Maintainers publish an update by pushing a stable tag such as `v0.2.0`. Configure
the public repository to protect `v*` tags from modification. No release archive
or package registry is required.

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
```

Each coordinator turn has a soft, cooperative time budget. The default is 300
seconds; select a positive, finite number of seconds for one fresh or resumed
turn with `--soft-phase-budget-seconds`:

```sh
bonaparte --soft-phase-budget-seconds 600 implement LIN-123
bonaparte --soft-phase-budget-seconds 120 resume <resume-token> "Continue"
```

The budget starts fresh for each coordinator turn. On expiry Bonaparte sends
exactly one native steer asking the coordinator to finish its current bounded
work and return a receipt. This is not a hard deadline or kill: work already in
progress may overrun the budget and report its result. Bonaparte requires a
Codex app-server that supports this native steering contract and fails clearly
when that contract is unavailable.

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
remain on disk for audit but cannot be resumed. If native delivery becomes
ambiguous, Bonaparte preserves the pending answer and reports the token instead
of silently restarting the phase. Token resumes reuse the saved model and
reasoning unless an explicit override is supplied. They also reuse the saved
soft phase budget unless `--soft-phase-budget-seconds` explicitly overrides it
for that resumed turn.

## Semantic progress for trusted hosts

Every fresh or resumed create, RCA, scope, implement, review, and publish run
has an optional, host-controlled progress channel. Before launching Bonaparte,
a trusted host may open a writable file descriptor numbered 3 or higher,
configure it as nonblocking, explicitly inherit it into the launcher, and set
`BONAPARTE_PROGRESS_FD` to that descriptor number. The launcher preserves the
descriptor when it replaces itself with the final runner. Update subprocesses
do not inherit the descriptor or its environment variable. No other transport
or progress setting exists.

The channel is UTF-8 JSON Lines using progress ABI version 2. Each record has
exactly `version`, `sequence`, `phase`, `state`, `elapsed_seconds`, and
`semantic`. `version` is `2`; `sequence` is a strictly increasing integer for
one process; `phase` is one of `create`, `rca`, `scope`, `implement`, `review`,
or `publish`; and `elapsed_seconds` is a nonnegative monotonic duration rounded
to milliseconds. A resume starts a new process sequence and elapsed clock while
restoring only its safe durable semantic snapshot.

`state` is one of `started`, `active`, `finalizing`, `completed`, `needs-input`,
`blocked`, `failed`, or `interrupted`. `semantic` is the latest snapshot plus
its bounded `milestones` list:

```json
{"version":2,"sequence":7,"phase":"implement","state":"active","elapsed_seconds":30.004,"semantic":{"stage":"checking","actor":"subagent-1","activity":"check","status":"completed","count":3,"milestones":[{"stage":"searching","actor":"coordinator","activity":"search","status":"completed","count":2},{"stage":"checking","actor":"subagent-1","activity":"check","status":"completed","count":3}],"milestones_total_count":2,"milestones_truncated":false}}
```

The snapshot and every milestone have exactly five typed fields: `stage`,
`actor`, `activity`, `status`, and `count`. Their allowed values are:

| Field | Allowed values |
|---|---|
| `stage` | `coordinating`, `searching`, `tool-use`, `checking`, `file-changes`, `subagent-assignment`, `subagent-completion`, `waiting-input`, `finalizing`, `terminal` |
| `actor` | `null`, `coordinator`, or an opaque per-run ordinal `subagent-N` where `N` is at least 1 |
| `activity` | `null`, `lifecycle`, `search`, `tool`, `check`, `file-change`, `subagent` |
| `status` | `null`, `started`, `in-progress`, `completed`, `failed`, `waiting`, `interrupted` |
| `count` | `null` or an integer from 0 through 2147483647; when present, the generic cumulative count for the current activity |

When milestones exist, `semantic` also contains `milestones`,
`milestones_total_count`, and `milestones_truncated`. The total is a
nonnegative integer no smaller than the retained list length, and the boolean
truncation flag reports whether earlier milestones were omitted. These three
fields are absent before the first milestone.

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

Progress ABI version 2 is intentionally incompatible with the former exact
review-only version 1 record. Hosts must update their parser before enabling the
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
