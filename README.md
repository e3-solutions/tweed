# Bonaparte

Bonaparte takes one software request from a human-readable Linear issue to a
reviewed, ready-for-review GitHub pull request. It is a thin wrapper around the
[official Codex SDK](https://learn.chatgpt.com/docs/codex-sdk): one SDK thread
per phase, one structured receipt per turn, and no hand-written app-server
transport.

```text
Bug:     create → RCA → scope → implement → review → publish
Feature: create → scope → implement → review → publish
```

Every phase after creation receives only the Linear issue identifier. Its fresh
coordinator reads the issue description and completed Bonaparte comments, then
writes one self-contained evidence-bearing comment before it can complete.
Coordinator conversations are not copied between phases, and there are no hidden
report files, local context databases, checkpoint envelopes, or event-normalizing
progress channels. The JSON receipt stays below 4 KiB and carries control state
and provenance only. When a phase needs clarification, the SDK thread ID resumes
that same native conversation.

The durable comments intentionally retain the material information needed by
the next phase: causal and repository evidence, affected files and boundaries,
decisions and objections, confidence and unresolved gaps, ordered work,
validation, Git provenance, review dispositions, and final delivery state. Raw
subagent transcripts and tool logs are never published.

## Install

Bonaparte uses `openai-codex==0.147.0`, which ships a pinned Codex runtime and
connects to the same Codex home, authentication, and MCP configuration. The
implement, review, and publish phases also use existing Git and GitHub CLI
authentication. Bonaparte does not pin a model and defaults coordinator reasoning
to `medium`.

Prerequisites:

- macOS or Linux with Git, Python 3.10+, and
  [uv](https://docs.astral.sh/uv/)
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

- `~/.local/bin/bonaparte` → the active release's SDK-backed script
- `~/.local/bin/autoresearch` → the active release's standalone research runner
- `~/.codex/skills/use-bonaparte` → the active release's Codex skill

The checkout can then move between branches or be deleted without changing the
installed behavior. If `~/.local/bin` is not already on `PATH`, add it to your
shell configuration:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Connect Codex to Linear and authenticate GitHub:

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

For a non-default location, set `BONAPARTE_BIN_DIR`, `BONAPARTE_HOME`, or
`CODEX_HOME` when running `./install`.

## Updating

Bonaparte has no background updater or release-switching launcher. Rerun the
installer from the desired tag or commit. It validates a new immutable snapshot
and atomically points the three managed symlinks at it. Existing non-symlink
targets are preserved and rejected.

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
bonaparte resume <phase> <resume-session-id> "clarification answer"
```

## Model selection

Select a model for one phase or for a resumed phase with `--model`:

```sh
bonaparte --model gpt-5.6-terra scope LIN-123
bonaparte --model gpt-5.6-luna resume scope <resume-session-id> "clarification answer"
```

Set one model for every Bonaparte phase in the environment:

```sh
export BONAPARTE_MODEL=gpt-5.6-terra
```

Precedence is `--model`, then `BONAPARTE_MODEL`, then Codex's configured model.

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
answer instead of restarting its investigation. A `needs-input` receipt contains
the SDK's `resume_session_id` and one material clarification question. Relay that
question to the user, then resume with the phase, session ID, and exact answer.
Bonaparte stores no parallel checkpoint; Codex owns thread persistence.

## Runtime layout

The executable is one PEP 723 script. `uv` installs the pinned `openai-codex`
dependency, whose bundled runtime owns app-server launch, JSON-RPC correlation,
thread persistence, structured output collection, and shutdown. Bonaparte owns
only phase prompts, receipt validation, CLI parsing, and workflow files.
