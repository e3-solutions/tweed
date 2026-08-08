# Bonaparte

Bonaparte takes one software request from a human-readable Linear issue to a
reviewed, ready-to-merge GitHub pull request. Each phase starts a fresh local
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

## Install

Bonaparte uses your local Codex installation and its authenticated Linear MCP. The
implement, review, and publish phases also use your existing Git and GitHub CLI
authentication.
Every phase coordinator is pinned to `gpt-5.6-sol` with medium reasoning, and
every spawned subagent is pinned to `gpt-5.6-sol` with medium reasoning.

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

## Updates

At most once per day, Bonaparte checks the public repository for the highest stable
`vX.Y.Z` tag. It fetches that exact Git ref into a new directory and smoke-tests
it before switching the active release atomically. A failed check never prevents
the installed runtime from starting.

```sh
bonaparte update
```

When upgrading an installation from before the `autoresearch` CLI was shipped,
the first command above runs the old launcher: it switches the active release
but cannot create a link it does not know about. Invoke Bonaparte once more so
the now-current launcher safely creates the missing link, then verify it:

```sh
bonaparte --help
autoresearch --help
```

The migration replaces only a missing link or an existing symlink. It refuses
and preserves a non-symlink at the autoresearch target path.

Set `BONAPARTE_AUTO_UPDATE=0` to disable the daily check. Run `./bonaparte` directly
when developing against a live checkout.

Maintainers publish an update by pushing a stable tag such as `v0.2.0`. Configure
the public repository to protect `v*` tags from modification. No release archive
or package registry is required.

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
bonaparte resume RCA <session-id> "clarification answer"
```

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
answer instead of restarting its investigation.
