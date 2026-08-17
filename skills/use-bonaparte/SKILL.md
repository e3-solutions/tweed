---
name: use-bonaparte
description: >-
  Run Bonaparte's isolated Linear-to-GitHub delivery workflow for software bugs
  and features through a ready-for-review pull request. Use when asked to record,
  investigate, scope, implement, review, publish, or resume a Bonaparte request.
  Bugs require evidence-backed RCA before scope; features begin at scope. Keeps
  the invoking task thin while phase coordinators own detailed work and return
  bounded receipts.
---

# Use Bonaparte

If `BONAPARTE_PHASE_CHILD=1`, execute the supplied phase workflow directly. Do not
invoke `bonaparte` or hand the assignment back to this skill; the CLI blocks nested
invocation as a fail-safe. Stop following this skill after this paragraph. The
instructions below apply only to the invoking task.

Keep this invoking task thin. Do not inspect the repository, read Linear,
investigate, or spawn subagents here. Each phase is exactly one command.
Invoke the bare `bonaparte` executable from `PATH`; the repository installer owns
that link. Do not search for or expect a runner inside this skill directory.
Run it with host write access because its updater and durable checkpoints live
under `$BONAPARTE_HOME`, outside a repository-only sandbox. If that access is
denied, request approval; never redirect checkpoints to a temporary directory.

Options precede the command name. Repeat run-wide options because every phase is
a fresh process; do not select an option the user did not request.

- Use `--model <model>` for the coordinator and its children. If omitted,
  `BONAPARTE_MODEL` and then Codex config apply.
- Use `--reasoning <effort>` for the coordinator and its children. It defaults
  to `medium`.
- Use `--soft-phase-budget-seconds <seconds>` only when the user selects a
  budget. Retain that flag across fresh phase commands; omit it to use the
  default 300-second soft budget. The value must be positive and finite.
- When the user names a PR base, append the quoted supplemental input
  `Expected pull-request base: <branch>` after the issue identifier on
  `implement`, `review`, and `publish`. Repeat it for all three phases. This is
  the PR target; Linear's `gitBranchName` remains the PR head.

```sh
bonaparte --repo <repository> --model gpt-5.6-sol --reasoning high scope <issue>
bonaparte --repo <repository> --model gpt-5.6-sol --reasoning high \
  implement <issue> "Expected pull-request base: staging"
bonaparte --repo <repository> --model gpt-5.6-sol --reasoning high \
  review <issue> "Expected pull-request base: staging"
bonaparte --repo <repository> --model gpt-5.6-sol --reasoning high \
  publish <issue> "Expected pull-request base: staging"
```

For a new request, classify it as a bug only when it reports incorrect existing
behavior; classify a requested capability as a feature. Assemble a compact
factual intake from the user's messages. Keep expected outcome, impact,
workflow, constraints, environment, examples, and evidence when supplied. For a
bug, also keep observed behavior and reproduction. Do not investigate or guess.
Include a named PR base in the intake as a delivery constraint, then also pass
the supplemental input above during delivery. Safely quote the intake and run:

```sh
bonaparte --repo <repository> create bug <factual intake>
bonaparte --repo <repository> create feature <factual intake>
```

For a full bug fix, run these fresh phases in order:

```sh
bonaparte --repo <repository> RCA <receipt.issue>
bonaparte --repo <repository> scope <receipt.issue>
bonaparte --repo <repository> implement <receipt.issue>
bonaparte --repo <repository> review <receipt.issue>
bonaparte --repo <repository> publish <receipt.issue>
```

For a full feature, skip RCA and run `scope`, `implement`, `review`, then
`publish`. Start each phase only when the prior receipt is `completed`, and pass
only the issue identifier returned by creation. Add the retained configuration
flags to these command shapes as described above.

If the user requests only one phase, run only that command. For an existing
issue, skip creation and start at the requested phase; do not infer an
unspecified issue kind by reading Linear in this task. Never paste the calling
conversation or an earlier phase report into a later command; Linear is the
handoff.

The runner calls the first working local `codex` on `PATH`, uses Codex's Linear
MCP without a model to select only the handoff required by the next phase, and
installs nothing. Treat each command's stdout as one JSON receipt of at most 4
KiB. Do not open coordinator/subagent tasks, Linear, or logs.

For every fresh or resumed phase, a trusted host may optionally open and
explicitly inherit a nonblocking file descriptor numbered 3 or higher, then set
`BONAPARTE_PROGRESS_FD` to its number. Progress JSONL uses ABI version 2 and
contains only fixed semantic stages, activities, statuses, counts, opaque actor
ordinals, and at most 32 deduplicated milestones. A host may continuously drain
and render those records while the one phase command runs, but must not poll
Bonaparte, interpret progress as a phase result, or expose coordinator data.
The channel is best effort; its absence or permanent failure requires no retry
or fallback. It never replaces the single stdout receipt of at most 4 KiB. The
invoking task remains thin and waits once for that final receipt.

On `needs-input`, relay only `question`. It should explain what the answer changes
and include supported options and a recommendation when evidence allows. Never
answer for the user or combine independent questions.

Soft-budget expiry asks the user to resume with `Continue`; any other question is
a material clarification. Continue the same coordinator with the exact user
answer as one safely quoted argument or structured process argument. Never
interpolate the answer into shell syntax. A token resume retains the model, reasoning,
repository, phase, budget, and native Codex thread. Pass configuration flags only
when the user intentionally overrides them:

```sh
bonaparte --repo <repository> [--model <model>] [--reasoning <effort>] \
  [--soft-phase-budget-seconds <seconds>] \
  resume <receipt.resume_token> <answer>
```

If the resumed phase returns another material question, repeat the exchange with
the same token. For a legacy receipt without `resume_token`, use
`resume <receipt.phase> <receipt.resume_session_id> <answer>` when its session ID
is present. Stop on `blocked` or `failed`; if a failed receipt includes a token,
report it with the blocker because the durable checkpoint remains available, but
never retry or reorder a phase automatically.
