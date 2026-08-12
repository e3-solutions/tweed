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

Honor model choices without choosing a model yourself. If the user selects one
model for the whole Bonaparte run, add `--model <model>` before the command name
on every phase and resume command. If the user selects models by phase, add the
matching flag only to those phase and resume commands. A model supplied on resume
may change the active coordinator's model. When the user makes no model choice,
omit the flag so the runner can honor `BONAPARTE_MODEL` or Codex configuration.

```sh
bonaparte --model <model> --repo <repository> scope <receipt.issue>
bonaparte --model <model> --repo <repository> resume \
  <receipt.phase> <receipt.resume_session_id> <answer>
```

For a new request, classify it as a bug only when it reports incorrect existing
behavior; classify a requested capability as a feature. Assemble a compact
factual intake from the user's messages. Keep expected outcome, impact,
workflow, constraints, environment, examples, and evidence when supplied. For a
bug, also keep observed behavior and reproduction. Do not investigate or guess.
Safely quote the intake and run one:

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
only the issue identifier returned by creation.

If the user requests only one phase, run only that command. For an existing
issue, skip creation and start at the requested phase; do not infer an
unspecified issue kind by reading Linear in this task. Never paste the calling
conversation or an earlier phase report into a later command; Linear is the
handoff.

The runner calls the first working local `codex` on `PATH`, uses Codex's Linear
MCP without a model to select only the handoff required by the next phase, and
installs nothing. Treat each command's stdout as one JSON receipt of at most 4
KiB. Do not open coordinator/subagent tasks, Linear, or logs.

Keep each phase command pending until process exit so the host resumes this task
once with the final receipt. Prefer one event-driven wait. If the host instead
returns a live process or session handle, wait on that same handle with empty
waits after 2, 5, 10, then 15 minutes, capped at 15 minutes. Do not emit progress
commentary, relaunch the command, or use `bonaparte status` as a completion poll.
If the user asks for progress, read `bonaparte status` once and report only its
compact phase, state, and elapsed time.

On `needs-input`, ask only `question`. If `resume_session_id` is present,
continue the same coordinator once:

```sh
bonaparte --repo <repository> resume <receipt.phase> <receipt.resume_session_id> <answer>
```

If it is null, rerun the phase once with its original input plus the question
and answer. Stop on `blocked` or `failed`; never reorder or otherwise retry a
phase automatically.
