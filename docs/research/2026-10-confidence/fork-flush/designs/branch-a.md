---
name: confidence-protocol
description: Implement, fix, refactor, research, or review software with explicit proof obligations, proportional verification, and traceable evidence. Use when the user requests Confidence Protocol or justified confidence in a software change.
---

# Confidence Protocol

Deliver the requested outcome with evidence a teammate can inspect. Command success, current source, and sufficient proof are separate judgments.

## Keep one requirement list

Keep one list of the accepted requirements from intake to report. Each item is exactly one of: **required** (needs current proof), **accepted exclusion** (out of scope or optional by the user's decision or settled scope, with the reason), or **open choice** (consequential and unanswered). For Standard/Critical repository work the list is the contract's `intent` and `proof_obligations`; otherwise it lives in the response. Create no other file for it. Every later event updates this list, not a side note: a recovered decision, an answer, a discovery, a failed check, a review finding, a scope or data error. An item changes from required to exclusion only by the user's decision or settled scope, never to finish; a necessary unknown fact stays required.

## Establish the contract

Use [intent and task flows](references/intent-flows.md) for new, ambiguous, or substantial work. First recover settled decisions from the conversation, existing contract, specs, repository guidance and retained evidence, and restate them so a wrong recovery is visible. Discover facts yourself; ask only the open choices, grouped, and continue independent preparation while waiting. A clear Quick task needs only a brief statement. Turn consequential claims into disprovable obligations. Trace the behavior through its execution and validation gates; a prerequisite that exists but is invalid must not enable an action or promise readiness.

For complex or long-running work, use [complex tasks](references/complex-tasks.md) to preserve dependencies, authority, blockers, review provenance, and recovery state. Use [harness guidance](references/harnesses.md) when delegating across Codex, Claude Code, or T3 Code. Resolve model and runtime capabilities from current documentation and actual receipts; a model name or agent count is not proof.

Use the lightest adequate process: **Quick** for clear, reversible local edits; **Standard** for ordinary bugs, features, and implementation-guiding research; **Critical** for consequential trust, money, destructive data, migration, or broad product changes. Use [mode examples](references/modes.md) and [task profiles](references/task-profiles.md) when the proof scope needs clarification. Explain the proof plan briefly. Preserve scope and existing authorization; continue discovery, implementation, repair, and verification autonomously. Ask only for an unresolved consequential choice or an action requiring additional authorization.

For substantial work, follow [model routing](references/model-routing.md). Claude Opus owns difficult implementation, diagnosis and repair, including its own check-and-repair loop; Claude Haiku takes bounded discovery or evidence extraction only when checking its output costs less than doing the work. When Codex coordinates, it keeps the user conversation, authority, integration and independent checks, and does not redo delegated work. The repair handoff is every required item a finding affects, including scope and data errors, each with the requirement, counterexample or source location, and the check; do not filter by finding type. An unavailable route falls back to direct work. Keep Quick work direct. Whoever claims completion verifies promoted findings; model output cannot close an obligation by itself.

## Build and challenge

Choose a small useful change that fits repository conventions. For bugs, reproduce the failure, separate competing causes with a targeted probe, and fix the causal boundary; then verify the trigger and important nearby behavior. Masking the symptom or weakening required validation is not a repair; loosening an incorrect overly strict guard can be. Read facts from the right repository, account, environment, entity and time through an authoritative accessible source: an MCP when appropriate, a CLI or local file when it answers the same boundary. Check freshness. Mocks establish only the behavior they retain; an offline mock is not live integration proof. If a claim depends on persistence or an external contract, run that boundary or mark the claim partial.

Use independent review for Critical work, consequential unresolved assumptions, changed trust/persistence/service contracts, surprising proof failures, or failures that are difficult to detect or undo. A reversible local mapping can use focused checks when it changes no such boundary; record why. Give the reviewer a narrow counterexample question and raw evidence. Critical work needs separate test-design and adversarial-review roles: independent proof design before implementation, adversarial review of the result. Retain reviewer origin, scope, findings, and a resolvable reference; never invent independence. An actor's check of its own implementation or repair is author evidence. For new Critical software contracts, use the pinned review records in [complex tasks](references/complex-tasks.md). If required review is unavailable, disclose the gap. Separately billed or cross-provider calls need authorization covering cost and source exposure.

Prefer one clear owner per rule, direct code, and abstractions justified by current needs. Tests check observable public behavior with small isolated fixtures, explicit or independently derived expectations (including property or relational checks) and clear failure messages, and, where relevant, a negative case that could reject the claim. A trivial documentation edit needs no new test. Avoid duplicated coverage and mocks that erase the tested boundary. Keep scratch copies, caches and symlinked dependencies from writing into files you do not own; others' work stays untouched.

## Verify and finish

Rerun affected proof after relevant code, test, or environment changes. Use the cheapest adequate probe and reuse current sufficient evidence; do not repeat adequate passing checks or broad suites without a relevant change. When the same failure repeats with no new facts, change the diagnostic, hypothesis or route; a justified retry of a suspected transient failure is acceptable. Keep a proven pre-send setup error, an unknown timeout or write outcome, and a failed required product behavior such as latency as separate findings.

For Standard/Critical repository work, read [evidence.md](references/evidence.md) for capture, recording, and completion semantics. Keep read-only requests read-only unless artifact creation is authorized. Successful validation checks evidence rules, not the truth of every product claim.

Before declaring completion, walk the requirement list. Pair each required item with the current executed check or inspected artifact that shows it, including a negative or boundary case where one could refute it; an unpaired item or unresolved counterexample is a required gap, and a worker's claim, a passing suite or review agreement does not close it. Report required gaps as partial, accepted exclusions separately with reasons, and open choices as open. Exclusions alone do not make the delivered scope incomplete.

Report delivered behavior, strongest relevant proof, remaining uncertainty, evidence location, and rollback when consequential. State exactly what was verified. Continue until the authorized outcome is delivered or a concrete blocker prevents further useful work.
