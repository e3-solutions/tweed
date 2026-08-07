# Bonaparte Create Request

Create one standardized Linear issue for the supplied `Kind: bug` or
`Kind: feature`. Use Linear MCP yourself. Do not inspect repository code, spawn
subagents, investigate causes, design a solution, comment, or implement.

Search for an obvious duplicate of the same kind and outcome. Reuse it when
found; otherwise create an issue in the team/project supported by the supplied
context. Ask one question instead of guessing when the destination is materially
ambiguous. Use an existing `Bug` or `Feature` label when appropriate, but do not
create workflow metadata or invent priority.

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
```

Preserve useful specifics and rewrite for clarity. Use `Unknown` for missing
facts. Never fabricate behavior, impact, reproduction, requirements, cause, or
solution. Add no comments: RCA owns the first Bonaparte comment for a bug, while
scope owns it for a feature.

Return only the provided receipt with `phase: create`, `result: created`, the
issue identifier and URL, and null Git/PR fields. Use `completed` only after the
issue exists. Use `needs-input` for one material destination question.
