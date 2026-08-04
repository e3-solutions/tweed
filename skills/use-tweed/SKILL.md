---
name: use-tweed
description: Invoke the local Tweed delivery runner through one bounded receipt. Use when a user asks Codex to create or advance a Tweed Linear issue, answer a Tweed clarification, resume an interrupted Tweed run, or retry pending Linear synchronization without loading child transcripts or reports.
---

# Use Tweed

Run exactly one command for the requested action:

```sh
tweed --agent create problem <request>
tweed --agent create feature <request>
tweed --agent root-cause <issue>
tweed --agent scope <issue>
tweed --agent implement <issue>
tweed --agent review <issue>
tweed --agent resume <run> [answer]
tweed --agent retry-sync <run>
```

Treat stdout as exactly one `dev.tweed.receipt.v1` JSON object of at most 4 KiB.
Do not ingest child output, task transcripts, polling output, run-state files, or
content-addressed reports. Do not start a second Tweed command automatically.

Handle the receipt by `state`:

- `created` or `completed`: Return the compact issue, stage, branch, commit, and summary.
- `awaiting-input`: Ask only the receipt's structured question. On a later user turn, invoke `resume` once with the answer.
- `sync-pending` or `sync-blocked`: Explain that reasoning and repository work are preserved. On explicit continuation, invoke `retry-sync` once; never rerun the phase.
- `blocked`, `partial`, or `not-established`: Return the summary and unchanged stage. Do not advance automatically.
- `failed` or `canceled`: Return the bounded error and run ID. If the user asks to continue an interrupted phase, invoke `resume` once without an answer.

Never use Linear tools directly. Tweed owns its deterministic Linear journal
adapter, phase coordinator, worktree, commit, and readiness gates.
