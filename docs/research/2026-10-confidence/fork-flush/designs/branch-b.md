---
name: confidence-protocol
description: Implement, fix, refactor, research, or review software with explicit proof obligations, proportional verification, and traceable evidence. Use when the user requests Confidence Protocol or justified confidence in a software change.
---

# Confidence Protocol

Deliver the requested outcome with evidence a teammate can inspect. Command success, current source, and sufficient proof are separate judgments.

## Establish the contract and its proof map

Recover settled decisions first: the conversation, an existing contract `intent`, accepted specs, repository guidance and retained evidence. Restate them briefly so a wrong recovery is visible. Use [intent and task flows](references/intent-flows.md) for new, ambiguous, or substantial work. Inspect sources for facts. Ask the user only about unresolved choices that change the outcome, acceptance, consequential risk or authority. Group those questions in one message, and continue independent discovery and preparation while you wait. A clear Quick task needs only a brief statement.

Use the lightest adequate process: **Quick** for clear, reversible local edits; **Standard** for ordinary bugs, features, and implementation-guiding research; **Critical** for consequential trust, money, destructive data, migration, or broad product changes. Use [mode examples](references/modes.md) and [task profiles](references/task-profiles.md) when the proof scope needs clarification. Preserve scope and existing authorization; continue discovery, implementation, repair, and verification autonomously. Ask only for an unresolved consequential choice or an action requiring additional authorization.

For Standard/Critical work, write the **proof map** before implementing. It lists each accepted requirement on one line with one status:

- `required`: what must happen or must never happen, the public interface that shows it, and the planned check. Include a negative or boundary case where one could refute the claim.
- `excluded`: an accepted non-goal or optional item, with its basis (the user, the contract or the stated scope).
- `open`: an unanswered choice or a necessary unknown fact. It blocks only the work that depends on it and counts as required until it is resolved. Never mark it excluded just to finish.

Keep the map in the existing contract `intent`/`proof_obligations`, or in the response for read-only work; it is not a new artifact. Unpaired `required` rows are the work queue. Update the affected row after every discovery, failed check, review finding, or scope or data error. Change a row's status only on user or contract basis. Trace actual behavior through its execution and validation gates; a prerequisite that exists but is invalid must not enable an action or promise readiness.

For complex or long-running work, use [complex tasks](references/complex-tasks.md) for dependencies, authority, blockers, review provenance and recovery. Use [harness guidance](references/harnesses.md) when delegating across Codex, Claude Code, or T3 Code. Resolve model and runtime capabilities from current documentation and actual receipts; a model name or agent count is not proof.

## Route and hand off

For substantial work, follow [model routing](references/model-routing.md). Claude Opus owns difficult implementation, diagnosis and repair, including its own check-and-repair loop. Claude Haiku is optional, only for bounded discovery or evidence extraction that costs less to check than to do. When Codex coordinates, it keeps the user conversation, authority, integration and independent checks, and does not redo delegated work. It returns every requirement-affecting finding to Opus, including scope, data, authority and source-choice errors, not only failing tests. Each finding goes back as a packet: the affected proof-map rows verbatim, the concrete counterexample or source location, and the reproducible check. An unavailable route falls back to direct work. Keep Quick work direct. Model output cannot close a proof obligation by itself.

## Build and challenge

Choose a small change that fits repository conventions. For bugs, reproduce the failure and locate the causal boundary. Then verify the trigger and important nearby behavior. A fix that masks the symptom or weakens required validation is not a repair. Correcting an incorrect, overly strict guard can be the root-cause fix. Read facts from the right repository, account, environment, entity and time through an authoritative accessible source: an MCP when appropriate, or a CLI or local file that answers the same boundary. Check freshness. An offline mock establishes only the behavior it retains, not live integration. If a claim depends on persistence or an external contract, run that boundary or mark the row partial.

Use independent review for Critical work, consequential unresolved assumptions, changed trust/persistence/service contracts, surprising proof failures, or failures that are hard to detect or undo. A reversible local mapping that changes no such boundary can use focused checks; record why. Give the reviewer a narrow counterexample question and raw evidence. Critical work needs separate test-design and adversarial-review roles: get independent proof design before implementation, then adversarial review of the result. Retain reviewer origin, scope, findings and a resolvable reference; never invent independence. An actor's check of its own implementation or repair is author evidence. For new Critical software contracts, use the pinned review records in [complex tasks](references/complex-tasks.md). Disclose unavailable required review. Separately billed or cross-provider calls need authorization covering cost and source exposure.

Prefer one clear owner per rule and direct code; remove unused scaffolding. Tests should check observable public behavior with small isolated fixtures and clear failures. Expectations may be explicit or independently derived property or relational checks. Avoid duplicated coverage and mocks that erase the tested boundary. A trivial documentation edit needs no forced red test. In scratch copies, keep writable dependencies local rather than symlinked, and confirm where checks write.

## Verify and finish

Rerun affected proof after relevant code, test, or environment changes. Reuse current sufficient evidence, use the cheapest adequate probe, and do not repeat adequate checks or broad suites without a relevant change. When a failure repeats with no new facts, change the diagnostic, hypothesis or route. A justified retry of a suspected transient failure is acceptable. Classify failures separately: a proven setup error before sending, a timeout or write with an unknown outcome, and failed required product latency. Stop when the accepted scope is complete.

For Standard/Critical repository work, read [evidence.md](references/evidence.md) for capture, recording, and completion semantics. Keep read-only requests read-only unless artifact creation is authorized. Successful validation checks evidence rules, not the truth of every product claim.

Before declaring completion, reread the proof map. Each `required` row needs the current executed check or inspected artifact that shows it. An unpaired row, an unresolved `open` row, or a known counterexample is a required gap. A completion claim, a passing suite, review agreement or a passing reference does not close it. Report three things separately:

- the delivered behavior with its strongest proof;
- required gaps, marked partial;
- accepted exclusions with reasons. These do not make the delivered scope incomplete.

Add remaining uncertainty, the evidence location and, when consequential, rollback. Continue until the authorized outcome is delivered or a concrete blocker prevents further useful work.
