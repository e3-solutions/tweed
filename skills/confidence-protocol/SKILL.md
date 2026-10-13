---
name: confidence-protocol
description: Implement, fix, refactor, research, or review software with explicit proof obligations, proportional verification, and traceable evidence. Use when the user requests Confidence Protocol or justified confidence in a software change.
---

# Confidence Protocol

Deliver the requested outcome with evidence a teammate can inspect. Command success, current source, and sufficient proof are separate judgments.

## Establish the contract

Understand the desired outcome before choosing an implementation. Use [intent and task flows](references/intent-flows.md) for new, ambiguous, or substantial work: recover known decisions, resolve consequential unknowns, choose the task flow, and map acceptance to proof. A clear Quick task needs only a brief statement. Identify observable success, important regressions, constraints, and unresolved facts before implementation. Turn consequential claims into disprovable obligations. Trace the actual behavior through its execution and validation gates; a prerequisite that exists but is invalid must not enable an action or promise readiness.

For complex or long-running work, use [complex tasks](references/complex-tasks.md) to preserve dependencies, authority, blockers, review provenance, and recovery state. Use [harness guidance](references/harnesses.md) when delegating across Codex, Claude Code, or T3 Code. Resolve model and runtime capabilities from current documentation and actual receipts; a model name or agent count is not proof.

Use the lightest adequate process: **Quick** for clear, reversible local edits; **Standard** for ordinary bugs, features, and implementation-guiding research; **Critical** for consequential trust, money, destructive data, migration, or broad product changes. Use [mode examples](references/modes.md) and [task profiles](references/task-profiles.md) when the proof scope needs clarification. Explain the proof plan briefly. Preserve scope and existing authorization; continue discovery, implementation, repair, and verification autonomously. Ask only for an unresolved consequential choice or an action requiring additional authorization. Finish authorized preparation before that decision.

For substantial work, follow [model routing](references/model-routing.md). Claude Opus owns difficult implementation, diagnosis and repair, including its own check-and-repair loop; Claude Haiku takes bounded discovery or evidence extraction only when checking its output costs less than doing the work. When Codex coordinates, it keeps the user conversation, authority, integration and independent checks, returns concrete requirement-affecting findings to Opus for repair, and does not redo delegated work. An unavailable route falls back to direct work. Keep Quick work direct. Whoever claims completion verifies promoted findings; model output cannot close a proof obligation by itself.

## Build and challenge

Choose a small useful change that fits repository conventions. For bugs, reproduce the failure, then verify the fix. Exercise important boundaries through public behavior; mocks establish only the behavior they retain. If a claim depends on persistence or an external contract, run that boundary or mark the claim partial.

Use independent review for Critical work, consequential unresolved assumptions, changed trust/persistence/service contracts, surprising proof failures, or failures that are difficult to detect or undo. A reversible local mapping can use focused checks when it changes no such boundary; record why. Give the reviewer a narrow counterexample question and raw evidence. Critical work needs separate test-design and adversarial-review roles. Obtain independent proof design before implementation; review the resulting change adversarially afterward. Retain reviewer origin, scope, findings, and a resolvable reference; never invent independence. An actor's check of its own implementation or repair is author evidence, not independent review of that change. For new Critical software contracts, use the pinned review records described in [complex tasks](references/complex-tasks.md). If required review is unavailable, disclose the gap. Use native delegation within task authorization; separately billed or cross-provider calls need authorization covering cost and source exposure. Preserve authorization already granted.

Prefer one clear owner per rule, direct code, and abstractions justified by current needs. Remove unused scaffolding. Tests should have small readable setup, literal failure messages, and cases that could reject the claim. Avoid duplicated coverage and mocks that erase the boundary being tested.

## Verify and finish

Rerun affected proof after relevant code, test, or environment changes. Reuse current sufficient evidence; do not repeat passing checks solely for ceremony. Resolve failures before expanding the test scope.

For Standard/Critical repository work, read [evidence.md](references/evidence.md) for capture, incremental recording, and completion semantics. Keep read-only requests read-only unless artifact creation is authorized. Required missing proof stays partial; optional exclusions remain visible with reasons. Successful validation checks evidence rules, not the truth of every product claim.

Before declaring completion, reread the accepted contract and pair each required behavior with the current executed check or inspected artifact that shows it, including a relevant negative or boundary case where one could refute the claim. An unpaired requirement or an unresolved known counterexample is a gap; a worker's completion claim, a passing suite, review agreement or a passing accepted reference does not close it.

Report delivered behavior, strongest relevant proof, remaining uncertainty, evidence location, and rollback when consequential. State exactly what was verified. Continue until the authorized outcome is delivered or a concrete blocker prevents further useful work.
