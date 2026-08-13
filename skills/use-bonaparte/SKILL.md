---
name: use-bonaparte
description: Take a software bug or feature from standardized Linear intake through the applicable isolated phases and a ready-to-merge GitHub pull request using bounded receipts. Bugs use evidence-backed RCA before solution scoping; features proceed directly to scope. Use when the user asks Bonaparte to record, investigate, build, solve, implement, review, or publish a software request, or asks for one Bonaparte phase on an existing Linear issue without loading child work into the current context.
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

Options precede the command name. Repeat run-wide options because every phase is
a fresh process; do not select an option the user did not request.

- Use `--model <model>` for the coordinator and its children. If omitted,
  `BONAPARTE_MODEL` and then Codex config apply.
- Use `--reasoning <effort>` for the coordinator and its children. It defaults
  to `medium`.
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

For review only, a trusted host may optionally open and explicitly inherit a
nonblocking file descriptor numbered 3 or higher, then set
`BONAPARTE_PROGRESS_FD` to its number. Consume that JSONL channel only as
best-effort liveness; it carries no review result, never replaces the single
bounded stdout receipt, and its absence or failure requires no retry or
fallback. The invoking task remains thin and waits for the final receipt.

On `needs-input`, ask only `question`. If `resume_session_id` is present,
continue the same coordinator once. Repeat that phase's model and reasoning
flags before `resume`; its original base instruction remains in the session:

```sh
bonaparte --repo <repository> [--model <model>] [--reasoning <effort>] \
  resume <receipt.phase> <receipt.resume_session_id> <answer>
```

If it is null, rerun the phase once with its original input plus the question
and answer. Stop on `blocked` or `failed`; never reorder or otherwise retry a
phase automatically.
