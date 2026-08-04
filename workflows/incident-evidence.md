# Tweed Incident Evidence Collector

Collect a bounded, read-only production evidence snapshot for the supplied incident policy. This is evidence collection only: do not diagnose a root cause, propose a solution, create or update tickets, modify repository files, deploy, or cause any external mutation.

## Rules

- Use only the model-facing MCP tools and direct-call MCP schemas explicitly exposed by the runner. Do not use shell or CLI substitutes for an MCP that is expected to supply the evidence.
- For a direct-call tool, return the exact `qualified_tool` and a compact JSON object encoded in `arguments_json`. Tweed parses and validates that string against the discovered tool schema, executes the configured stdio MCP transport itself, and returns the genuine result in the same collector session. Plan only one dependency layer per round: for example, resolve a project before using its ID to resolve services, then query those services.
- Query only the closed UTC window in the incident policy. If a tool cannot express that window, disclose the limitation and use the narrowest available read.
- When a direct tool exposes `since` and `until`, Tweed deterministically replaces both with the frozen policy bounds before the call and records those actual normalized arguments.
- Collect enough independent evidence to characterize candidate incidents, their confirmed impact, relevant health/configuration, and existing Linear/GitHub work, without bulk-exporting unrelated production data.
- Every production or existing-work claim used later must come from an actual successful MCP call. The runner records model-facing calls from the Codex turn and direct stdio JSON-RPC responses from its own transport; prose citations are not receipts.
- A direct-call error is also returned as a signed runner receipt so you can narrow or replace the query. It is not evidence for a production claim. Do not repeat the same failed call unchanged.
- Do not spawn agents. Do not repeat a successful query unless the result is incomplete or contradictory.
- If required access is unavailable or the allowed tools cannot establish useful evidence, return `blocked` rather than guessing.

## Output

Return the runner's structured object with:

- `status`: `collected` or `blocked`
- `summary`: a concise statement of coverage or the exact blocker
- `coverage`: a concise list of systems and time bounds actually checked
- `direct_calls`: the next bounded dependency layer of runner-executed MCP calls, or an empty list when collection is complete or blocked

Do not include raw logs or tool output in the final response; the runner freezes them directly from the tool-call records.
