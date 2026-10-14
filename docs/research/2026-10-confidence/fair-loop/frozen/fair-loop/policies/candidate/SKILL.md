---
name: confidence-protocol
description: Implement, fix, refactor, research, or review software with explicit proof obligations, proportional verification, and traceable evidence. Use when the user requests Confidence Protocol or justified confidence in a software change.
---

# Confidence Protocol

Deliver the requested outcome with evidence a teammate can inspect. Command success, current source, and sufficient proof are separate judgments.

## Default loop

Ordinary work follows one loop: contract, proof plan, change, check and repair, close. Add process only where the risk rules below call for it, and continue autonomously until the authorized outcome is delivered or a concrete blocker remains.

1. **Contract.** State the goal, the required behaviors, what must not happen or change, and the scope boundary: the paths, interfaces, data and environment the task may read or change. Recover settled decisions and discover facts from the conversation, repository and retained evidence before asking. Ask only when an open choice would change the outcome, acceptance, consequential risk or authority; then ask the current frontier once, grouped, as in [intent and task flows](references/intent-flows.md) and [question patterns](references/question-patterns.md). Otherwise state assumptions and proceed. A necessary fact that is still unknown stays a required gap.
2. **Proof plan.** For each required behavior, name the public interface that shows it, an expected result derived from the requirement rather than from the code, and a negative or boundary case that could refute it.
3. **Change.** Make the smallest change that fits repository conventions and stays inside the scope boundary; report a worthwhile change outside it as a suggestion.
4. **Check and repair.** Run the planned checks against the current source and repair from what a failed check actually showed. As soon as a repeated attempt adds no new facts, change the diagnostic, hypothesis or route, or report a precise blocker; a justified diagnostic retry of a suspected transient failure remains acceptable, and no fixed number of attempts is required first.
5. **Close.** Pair each required behavior, each negative case and the scope boundary (the actual changed paths) with current evidence, as described under Verify and finish.

## Establish the contract

Understand the desired outcome before choosing an implementation. Use [intent and task flows](references/intent-flows.md) for new, ambiguous, or substantial work: recover known decisions, resolve consequential unknowns, choose the task flow, and map acceptance to proof. A clear Quick task needs only a brief statement. Turn consequential claims into disprovable obligations. Trace the actual behavior through its execution and validation gates; a prerequisite that exists but is invalid must not enable an action or promise readiness.

For complex or long-running work, use [complex tasks](references/complex-tasks.md) to preserve dependencies, authority, blockers, review provenance, and recovery state. Use [harness guidance](references/harnesses.md) when delegating across Codex, Claude Code, or T3 Code. Resolve model and runtime capabilities from current documentation and actual receipts; a model name or agent count is not proof.

Use the lightest adequate process: **Quick** for clear, reversible local edits; **Standard** for ordinary bugs, features, and implementation-guiding research; **Critical** for consequential trust, money, destructive data, migration, or broad product changes. Use [mode examples](references/modes.md) and [task profiles](references/task-profiles.md) when the proof scope needs clarification. Explain the proof plan briefly. Preserve scope and existing authorization. Finish authorized preparation before that decision.

For substantial work, follow [model routing](references/model-routing.md). Claude Opus owns difficult implementation, diagnosis and repair, including its own check-and-repair loop; Claude Haiku takes bounded discovery or evidence extraction only when checking its output costs less than doing the work. When Codex coordinates, it keeps the user conversation, authority, integration and independent checks, returns concrete requirement-affecting findings, including scope and data errors, to Opus for repair, and does not redo delegated work. An unavailable route falls back to direct work. Keep Quick work direct. Whoever claims completion verifies promoted findings; model output cannot close a proof obligation by itself.

## Build and challenge

Choose a small useful change that fits repository conventions. For bugs, reproduce the failure, locate its cause, then verify the trigger and important nearby behavior; a fix that masks the symptom or weakens required validation is not a repair, while correcting an overly strict, incorrect guard can be the root-cause fix. Read facts from the right repository, account, environment, entity and time through an authoritative accessible source: an MCP when appropriate, a CLI or local file when it answers the same boundary. Exercise important boundaries through public behavior; mocks establish only the behavior they retain, and an offline mock is not live integration proof. If a claim depends on persistence or an external contract, run that boundary or mark the claim partial.

Use independent review for Critical work, consequential unresolved assumptions, changed trust/persistence/service contracts, surprising proof failures, or failures that are difficult to detect or undo. A reversible local mapping can use focused checks when it changes no such boundary; record why. Give the reviewer a narrow counterexample question and raw evidence. Critical work needs separate test-design and adversarial-review roles. Obtain independent proof design before implementation; review the resulting change adversarially afterward. Retain reviewer origin, scope, findings, and a resolvable reference; never invent independence. An actor's check of its own implementation or repair is author evidence, not independent review of that change. For new Critical software contracts, use the pinned review records described in [complex tasks](references/complex-tasks.md). If required review is unavailable, disclose the gap. Use native delegation within task authorization; separately billed or cross-provider calls need authorization covering cost and source exposure. Preserve authorization already granted.

Prefer one clear owner per rule, direct code, and abstractions justified by current needs. Remove unused scaffolding. Tests should check observable public behavior with small isolated fixtures, explicit or independently derived expectations and clear failure messages, and, where relevant, a negative case that could reject the claim; a trivial documentation edit needs no forced red test or new test. Avoid duplicated coverage and mocks that erase the boundary being tested. Add or change ordinary tests when that helps; when a requirement changes expected behavior, update the affected expectation, name the requirement that justifies it, and keep unrelated regression checks intact. Never weaken, skip or replace an independent owner check, acceptance fixture or negative case to make it pass.

When findings arrive from a reviewer, critic or owner check, including scope and data-boundary verdicts, handle the complete set as claims about the current source, as in [model routing](references/model-routing.md): reproduce or inspect each, then repair it or reject it with contradicting evidence; do not drop one silently. After a handoff or fresh context, rebuild state from durable material (the contract, current diff, latest check output and open findings) rather than from summary pass labels.

## Verify and finish

Rerun affected proof after relevant code, test, or environment changes. Use the cheapest adequate probe and reuse current sufficient evidence; do not repeat adequate passing checks or broad suites without a relevant change. Resolve failures before expanding the test scope. Stop when the accepted scope is complete.

For Standard/Critical repository work, use [evidence.md](references/evidence.md) for capture, incremental recording, and completion semantics when its evidence CLI is available in the task environment; otherwise keep the same claim-to-evidence pairing in the report. A focused Standard task does not need a CLI certificate. Keep read-only requests read-only unless artifact creation is authorized. Required missing proof stays partial; accepted or optional exclusions remain visible with reasons, separate from required gaps, and do not by themselves make the delivered scope incomplete. Successful validation checks evidence rules, not the truth of every product claim.

Before declaring completion, reread the accepted contract and pair each required behavior and the scope boundary (compare the actual changed paths) with the current executed check or inspected artifact that shows it, including a relevant negative or boundary case where one could refute the claim. An unpaired requirement, an unresolved known counterexample or proof that predates a relevant edit is a gap; a worker's completion claim, a passing suite, review agreement or a passing accepted reference does not close it.

Report delivered behavior, strongest relevant proof, remaining uncertainty, evidence location, and rollback when consequential. State exactly what was verified.
