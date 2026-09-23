---
name: confidence-protocol
description: Implement, fix, refactor, research, or review software with explicit proof obligations, proportional verification, and traceable evidence. Use when the user requests Confidence Protocol or justified confidence in a software change.
---

# Confidence Protocol

Deliver the requested outcome with evidence a teammate can inspect. Command success, current source, and sufficient proof are separate judgments.

## Establish the contract

Identify observable success, important regressions, constraints, and unresolved facts before implementation. Turn consequential claims into disprovable obligations. Trace the actual behavior through its execution and validation gates; a prerequisite that exists but is invalid must not enable an action or promise readiness.

Use the lightest adequate process: **Quick** for clear, reversible local edits; **Standard** for ordinary bugs, features, and implementation-guiding research; **Critical** for consequential trust, money, destructive data, migration, or broad product changes. Use [mode examples](references/modes.md) and [task profiles](references/task-profiles.md) when the proof scope needs clarification. Explain the proof plan briefly. Preserve scope and existing authorization; continue discovery, implementation, repair, and verification autonomously. Ask only for an unresolved consequential choice or an action requiring additional authorization. Finish authorized preparation before that decision.

## Build and challenge

Choose a small useful change that fits repository conventions. For bugs, reproduce the failure, then verify the fix. Exercise important boundaries through public behavior; mocks establish only the behavior they retain. If a claim depends on persistence or an external contract, run that boundary or mark the claim partial.

Use independent review for Critical work, consequential unresolved assumptions, changed trust/persistence/service contracts, surprising proof failures, or failures that are difficult to detect or undo. A reversible local mapping can use focused checks when it changes no such boundary; record why. Brief reviewers with [review.md](references/review.md): they work independently, check the change backward from what must not break, and report only findings with proof. Reviewers report; the owner fixes and ends each finding as fixed, refuted, or accepted risk. Critical work needs separate test-design and adversarial-review roles. Obtain independent proof design before implementation; review the resulting change adversarially afterward. Retain reviewer origin, scope, findings, and a resolvable reference; never invent independence. If required review is unavailable, disclose the gap. External model calls need authorization covering cost and data exposure.

Prefer one clear owner per rule, direct code, and abstractions justified by current needs. Remove unused scaffolding. Tests should have small readable setup, literal failure messages, and cases that could reject the claim. Avoid duplicated coverage and mocks that erase the boundary being tested.

## Verify and finish

Rerun affected proof after relevant code, test, or environment changes. Reuse current sufficient evidence; do not repeat passing checks solely for ceremony. Resolve failures before expanding the test scope.

For Standard/Critical repository work, read [evidence.md](references/evidence.md) for capture, incremental recording, and completion semantics. Keep read-only requests read-only unless artifact creation is authorized. Required missing proof stays partial; optional exclusions remain visible with reasons. Successful validation checks evidence rules, not the truth of every product claim.

Report delivered behavior, strongest relevant proof, remaining uncertainty, evidence location, and rollback when consequential. State exactly what was verified. Continue until the authorized outcome is delivered or a concrete blocker prevents further useful work.
