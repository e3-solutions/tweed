# Bonaparte Create Request

Create one standardized Linear issue for the supplied `Kind: bug` or
`Kind: feature`. Use Linear MCP yourself. Do not inspect repository code, spawn
subagents, investigate causes, design a solution, comment, or implement.

Search once for an obvious duplicate. Reuse only one active, nonterminal match
of kind, affected surface, and outcome; never mutate or reopen it. Ask one exact
question for multiple plausible matches or a materially ambiguous destination.
Otherwise create in the supported team/project. Reuse an existing `Bug` or
`Feature` label when appropriate, but do not create metadata or invent priority.

Generate a concise human title from the reported behavior or requested
capability. Do not use the raw prompt, command text, a generic label, hash, or
protocol token as the title.

The description must contain exactly these top-level sections:

```markdown
## What
**Kind:** Bug | Feature

[For a bug: observed and expected behavior, affected surface, and original
report. For a feature: requested capability, current limitation, affected users
or workflow, and original request.]

## Why
[Known user or business impact, value, urgency, and why it matters.]

## How
[Known trigger or workflow, examples, environment, frequency, constraints, and
supplied evidence. Describe inputs and desired outcomes, not a speculative
implementation.]

Bonaparte phase token: [exact runner-supplied canonical token]
```

Preserve useful specifics and rewrite for clarity. Use `Unknown` for missing
facts. Never fabricate behavior, impact, reproduction, requirements, cause, or
solution. For a newly created issue, the runner supplies the exact correlation
line separately; preserve it verbatim inside `## How`. It is private control
metadata used only for exact receipt-loss readback and must not be replaced by a
title or fuzzy search. Do not mutate a reused pre-existing issue solely to add a
marker. Add no comments: RCA owns the first Bonaparte comment for a bug, while
scope owns it for a feature.

After creation or reuse, re-read the selected issue and verify its destination,
kind, title, required description sections, identifier, and URL. Complete only
from that verified record.

Return only the provided receipt with `phase: create`, `result: created`, the
issue identifier and URL, and null Git/PR fields. Use `completed` only after the
issue exists. Use `needs-input` for one material destination question.
