---
name: use-tweed
description: Take a software bug or feature from standardized Linear intake through the applicable isolated phases and a ready-to-merge GitHub pull request using bounded receipts. Bugs use evidence-backed RCA before solution scoping; features proceed directly to scope. Use when the user asks Tweed to record, investigate, build, solve, implement, review, or publish a software request, or asks for one Tweed phase on an existing Linear issue without loading child work into the current context.
---

# Use Tweed

If `TWEED_PHASE_CHILD=1`, this task is already the phase coordinator. Do not
invoke `tweed` or hand the assignment back to this skill. Execute the supplied
phase workflow directly and return its requested receipt. The CLI also rejects
nested invocation as a fail-safe.

Keep this invoking task thin. Do not inspect the repository, read Linear,
investigate, or spawn subagents here. Each phase is exactly one command.
Invoke the bare `tweed` executable from `PATH`; the repository installer owns
that link. Do not search for or expect a runner inside this skill directory.

For a new request, classify it as a bug only when it reports incorrect existing
behavior; classify a requested capability as a feature. Assemble a compact
factual intake from the user's messages. Keep expected outcome, impact,
workflow, constraints, environment, examples, and evidence when supplied. For a
bug, also keep observed behavior and reproduction. Do not investigate or guess.
Safely quote the intake and run one:

```sh
tweed --repo <repository> create bug <factual intake>
tweed --repo <repository> create feature <factual intake>
```

For a full bug fix, run these fresh phases in order:

```sh
tweed --repo <repository> RCA <receipt.issue>
tweed --repo <repository> scope <receipt.issue>
tweed --repo <repository> implement <receipt.issue>
tweed --repo <repository> review <receipt.issue>
tweed --repo <repository> publish <receipt.issue>
```

For a full feature, skip RCA and run `scope`, `implement`, `review`, then
`publish`. Start each phase only when the prior receipt is `completed`, and pass
only the issue identifier returned by creation.

If the user requests only one phase, run only that command. For an existing
issue, skip creation and start at the requested phase; do not infer an
unspecified issue kind by reading Linear in this task. Never paste the calling
conversation or an earlier phase report into a later command; Linear is the
handoff.

The runner calls the first working local `codex` on `PATH`, using its existing
Linear MCP, and installs nothing. Treat each command's stdout as one JSON receipt
of at most 4 KiB. Do not open coordinator/subagent tasks, Linear, or logs.

On `needs-input`, ask only `question`. On the user's next turn, continue the
same coordinator session exactly once:

```sh
tweed --repo <repository> resume <receipt.phase> <receipt.resume_session_id> <answer>
```

Never rerun a phase after clarification. Stop on `blocked` or `failed` and
return the receipt directly. Never bypass, reorder, or retry a phase
automatically.
