---
name: bonaparte
description: Coordinate context-isolated adversarial subagents to take a software bug or feature from a user request or Linear issue through evidence-backed investigation, minimal implementation, verification, review, and a ready-for-review GitHub pull request. Use when asked to run Bonaparte; record, investigate, scope, implement, review, publish, or resume a software request with a durable handoff; fix a bug end to end; build a feature from a ticket; or turn a Linear issue into a reviewed PR. Do not use for a review-only request that does not ask for Bonaparte or end-to-end delivery.
---

# Bonaparte

Deliver one software request through context-isolated adversarial subagents. Preserve blindness,
reconcile evidence, integrate work, and own user communication and external writes. Use subagents
to investigate, challenge, write bounded packets, and perform non-author review—not as extra hands
driven toward a preferred conclusion.

## Adversarial contract

- Before each phase, write its **decision frontier**: unresolved questions whose answers could
  change cause, scope, behavior, interfaces, proof, or readiness. Every frontier question requires an evidence-bearing,
  context-isolated challenge before commitment. Use zero subagents only for a fully mechanical,
  locally provable operation with an explicit outcome, surface, and decisive check.
- Route agents with the topology below. Counts are conservative Bonaparte assurance defaults,
  not research-established universal optima. Up-route only for a distinct unresolved question or
  evidence channel; down-route only under the stated deterministic-evidence rule.
- Stop if required subagents are unavailable or prohibited. The coordinator's second pass is not
  non-author review. After spawning, verify every required agent has a live identity. A failed spawn, missing agent ID, or empty wait target means the gate is unavailable.
- Brief blind first-pass agents with immutable raw facts: request, repository and exact `HEAD`,
  constraints, evidence, boundary, one distinct question, return schema, and stop condition. Hide
  coordinator hypotheses, other reports, intended fixes, and author rationale.
- For blind or fresh roles, spawn with no inherited conversation turns, or the smallest fork that
  provably excludes those conclusions. Send a self-contained sanitized brief. Otherwise stop: the
  context-isolation gate is unavailable.
- Fresh threads reduce anchoring; they do not imply statistical independence when agents share a
  model, tools, training, or evidence. Prefer different falsifiable objectives, evidence sources,
  tools, or models when available. Cloned prompts produce correlated answers, not diversity.
- Collect all blind reports before sharing conclusions. A later falsifier may receive the candidate
  claim and cited evidence, but never ask an agent merely to confirm a favored theory.
- Separate ownership: an investigator does not approve its own causal claim; a writer may not
  review its own change; the coordinator does not replace required adversarial work with self-review.
- Resolve disagreement through a reproduction, test, trace, contract lookup, or exact diff check.
  A vote or calibrated confidence may route the next diagnostic but cannot establish software correctness.
  Preserve material dissent until a discriminator resolves it.
- Keep the invoking task cohesive. Subagents make no Linear, GitHub, branch, commit, push, merge,
  deploy, or other external writes. Give each file or implementation surface one writer; the
  coordinator owns integration and remote mutations.
- Ask one concise question only when a user-owned choice or missing authority changes the result.
  Investigate discoverable facts.

## Adaptive phase councils

`Fresh` means a new context-isolated thread for the phase. Do not reuse an investigator in a later
phase, make a writer its reviewer, or count the coordinator as the adversarial challenger.
Spawn no more than `3` concurrently.

| Phase | Default topology | Routing rule |
|---|---|---|
| Bug investigation / RCA | 2 blind read-only: causal tracer; competing-hypothesis falsifier | Keep both when cause, incident attribution, or oracle is uncertain. One context-isolated investigator plus a direct reproduction may suffice only when that check proves a local mechanism and rejects the strongest credible alternative. Add a reproducer for missing runtime evidence. |
| Feature investigation | 2 blind read-only: current-state/reuse explorer; outcome/risk/proof analyst | Keep both for multiple consumers, competing designs, or non-local risk. One explorer may suffice only when a direct repository check settles current behavior, the local outcome, and lack of competing design. |
| Scope | Fresh post-synthesis minimalist challenger; mechanism/change mapper by default | Omit the mapper only when investigation already proves the local surface and dependency edges. The challenger is never omitted for judgment-bearing scope. Add a specialist only for a named unresolved boundary. |
| Implementation | Bounded writer using an accepted proof artifact | Add a fresh proof/test designer when the regression, oracle, or integration proof is ambiguous, novel, or high risk. Add packet review only before dependent work consumes an independently reviewable packet. |
| Final review | Fresh non-writing whole-diff reviewer; 2 complementary reviewers by default | Require the second for non-local work, multiple consumers, public interfaces, security, persistence, concurrency, migration, cross-service behavior, ambiguous proof, or judgment-dependent acceptance. One may suffice for a local low-risk diff with a decisive executable regression and no dissent. Add a specialist for an exact elevated risk or conflict. |
| Delivery | Deterministic coordinator checks | Add a fresh readiness auditor only for ambiguous ancestry, ownership, duplicate/mismatched PR state, or disputed evidence. |

Intake, test execution, and final mutation remain coordinator-owned and mechanical; they do not
replace the next judgment gate. A named phase runs its complete entry gate and routed topology.
When a direct check resolves the sole uncertainty, do not retain or add an LLM seat merely to satisfy headcount; record the check and reduced-route basis.

Use these compact report formats:

```text
Investigation: Claim | Evidence (file:line or diagnostic + result) | Strongest alternative |
Contradicting evidence | Confidence | Missing evidence | Smallest decisive next check

Finding: ID/criterion | Material consequence | Reproducible evidence | Minimum correction |
Proving check | Verdict: pass/fail/unverified
```

Unsupported opinion, generic hardening, and stylistic preference are not adversarial evidence.

## Council protocol

1. **Freeze facts.** Record request, exact `HEAD`, worktree state, relevant paths, contract, and
   allowed evidence. For candidate review, freeze:
   - **Task manifest:** intended base and `HEAD`; each task-owned path's resulting content/blob hash
     and mode or deletion; staged/unstaged state; each task-owned untracked path, hash, and intended
     disposition; task-only diff hash; contract hash.
   - **Ambient manifest:** each non-task staged, unstaged, and untracked path with content and mode
     hashes. Ambient work never enters the reviewed task diff or commit and must remain unchanged.
   Give reviewers the task manifest and complete task-only diff. Freeze task content during review.
2. **Diverge first.** Dispatch read-only first passes together with distinct questions and identical
   immutable facts. Collect all reports before cross-agent messages.
3. **Reconcile centrally.** Record agreed facts and conflicts. For one rebuttal round, send only the
   opposing claim and evidence; do not broadcast transcripts or invite open-ended group discussion. This round limit
   is operational, not a research optimum.
4. **Discriminate.** Run the smallest executable check. Votes or agreement may prioritize but never
   close a directly testable proof obligation.
5. **Invalidate stale review.** Any task content, contract, or proof change creates a new manifest
   and discards affected review credit. Retain review across a content-preserving commit only after
   proving committed task paths and intended untracked dispositions equal the task manifest and the
   ambient manifest is unchanged.
6. **Bound convergence.** Continue only while a diagnostic or correction adds evidence, shrinks the
   diff, or lowers severity. Use three finding-bearing rounds as an operational ceiling; return to
   scope or stop earlier on repeated non-progress. This is not a research result.

## Phase entry contract

Every phase needs `request`, `phase`, `repository`, exact `HEAD`, `raw-constraints`, and
`ambient-manifest`. Require only its additional row; do not demand the phase's own outputs.

| Phase | Additional required entry fields |
|---|---|
| Record / intake | None |
| Bug investigation | `observed-behavior`, `expected-behavior`; `reproduction-or-incident-evidence` when available |
| Feature investigation | `requested-outcome`, `current-limitation` |
| Scope | `reconciled-investigation`, `material-dissent`, `affected-consumers`; `bug-rca` for a bug |
| Implementation | `accepted-outcome`, `change-surface`, `non-goals`, `dependency-impact-graph`, `risks`, `acceptance-criteria`, `proof-obligations` |
| Review | `implementation-contract`, `intended-base`, `task-manifest`, `task-only-diff`, `affected-consumers`, `proof-obligations` |
| Delivery | `reviewed-task-manifest`, `review-verdicts`, `exact-validation`; `issue-branch-commit-pr-identity` when applicable |

Carry the contract between phases in one task. Use Linear comments as the durable handoff when
Linear is involved. For a resumed local phase, require the user or repository to expose its matrix
row. Stop and name missing fields; never invent them, run another phase silently, or rely on hidden
agent history.

Default to intake -> investigation -> reconciliation -> scope -> implementation -> verification ->
adversarial review -> ready-for-review PR -> Linear delivery note. Run only the named phase when
requested. Never turn record-, investigation-, scope-, or review-only work into code or remote writes.
Bugs require established causation before scope; features require verified current behavior.

Keep workflow state explicit in the invoking task and the repository or external records named in
the phase contract; do not rely on hidden agent history. Preserve user work: Never reset, clean,
discard, overwrite, or stash unrelated changes. Never force-push,
rewrite shared history, merge, or deploy. Re-read external writes. On retry, inspect and resume the
exact issue, branch, and PR; Do not create duplicates.

## 1. Establish the request

1. Read repository instructions. Record path, branch, exact `HEAD`, remotes, and staged, unstaged,
   and untracked paths.
2. Read the supplied Linear issue. When asked to record or deliver a request without an issue,
   search once for an obvious active duplicate; create one only when absent. Record facts without
   inventing cause or design: kind, observed/expected behavior or capability/current limit, impact,
   reproduction/workflow, environment, constraints, and evidence. Mark unknowns; re-read the issue.
3. Stop before editing if unrelated changes overlap the request. Treat an apparent interrupted
   attempt as an untrusted candidate: inspect and test it without discarding or crediting it.

Stop here for a record-only request.

## 2. Investigate blindly

### Bugs

Route from the topology. By default, give identical raw facts to:

- **Causal tracer:** reproduce when feasible; trace trigger to failure across callers, state, data,
  configuration, dependencies, and external boundaries.
- **Competing-hypothesis falsifier:** seek an alternative cause, counterexample, omitted consumer,
  boundary condition, or evidence that the obvious explanation is only correlated.

Collect routed reports blind. Use the one-agent route only when the recorded direct reproduction
proves the local mechanism and rejects the strongest credible alternative. Add a fresh evidence
collector when incident/runtime attribution is material but indirect. Require trigger, responsible
boundary, mechanism, alternative, exact evidence, and missing check. Static code shows susceptibility,
not incident cause. For time-dependent incidents, require matching reproduction or correlated runtime
evidence. Test a proposed patch's invariant over its full lifetime/boundary—not merely the presence of
a header, lock, retry, transaction, or validation call.

### Features

Route from the topology. By default, give identical raw facts to:

- **Current-state/reuse explorer:** trace workflow, consumers, conventions, interfaces, tests, and
  current boundary behavior.
- **Outcome/risk/proof analyst:** derive observable acceptance and seek compatibility, security,
  data, concurrency, performance, migration, or simpler-mechanism concerns.

Use one explorer only when the decision frontier cites the direct check settling current behavior,
local outcome, and lack of competing design. Separate requested behavior from proposed implementation.
Use current primary documentation only for version-sensitive contracts repository evidence cannot
settle; share the source and version with all routed agents.

Stop here for an investigation-only request. Reconcile first; report conclusion, decisive evidence,
material dissent, confidence, and missing proof.

## 3. Reconcile before scope

Build `Claim | Supporting evidence | Contradicting evidence | Confidence | Decisive check`. Give each
side only the opposing claim and evidence for one rebuttal when conflict could change cause, scope,
behavior, interface, or proof. Run the smallest discriminating diagnostic; add a fresh tie-break investigator only
when its execution or interpretation needs context isolation. Directly inspect the decisive evidence.

For bugs, pass RCA only with trigger, responsible code/configuration/data/dependency/environment,
causal mechanism, and evidence rejecting the strongest alternative. Stop or ask one user-owned
question if material disagreement survives the rebuttal and smallest available check.

## 4. Define and challenge scope

Draft from reconciled claims:

- **Outcome/Basis:** observable behavior and established bug mechanism or feature limitation.
- **Change surface:** files/boundaries with one responsibility each.
- **Dependency/change-impact graph:** affected consumers, interface/data/control edges, packet order,
  and replanning triggers.
- **Acceptance:** trigger -> observable result -> decisive check.
- **Non-goals/Risks:** explicit exclusions and proportional safeguards.

Unless investigation already proves the local surface and edges, ask a fresh read-only mapper for the
smallest coherent surface, graph, packet order, and proof obligations. Then give a fresh **scope
challenger** the raw request, evidence table, and draft. Require independently derived acceptance,
attacks on every material inclusion/exclusion, omitted consumers, and unnecessary dependencies,
abstractions, configuration, schemas, migrations, or compatibility layers. Add a boundary specialist
only for a named unresolved non-local risk. Resolve design-affecting objections before editing.

For a Linear-backed full workflow, post and re-read one concise `## Bonaparte · Plan` contract.
Skip it for local-only or scope-only work unless requested.

Stop here for a scope-only request. Complete the context-isolated challenge first.

## 5. Implement bounded packets

1. Choose the issue branch from the official name, repository instructions, or a short issue-based
   name. Validate ref and base without rewriting history.
2. Split only into independently testable vertical packets. Keep coupled files and behavior together.
3. Before editing, accept a **proof artifact** mapping each criterion to its oracle, pre/current result,
   expected candidate result, consumers, and exact check. Existing regression tests or deterministic
   analysis may supply an unambiguous artifact. For an ambiguous, novel, or high-risk oracle, use a
   fresh proof/test designer given raw evidence—not a patch. Reconcile its report into the packet and
   writer brief. Do not spawn a writer or permit edits before acceptance.
4. Only then give a separate writer one bounded packet, owned paths, accepted obligations, checks,
   and stop condition. It must not invent product, architecture, dependency, schema, migration, or
   interface decisions; return deviations to scope.
5. Use one owner per surface. Serialize writers and packet review in a shared worktree. Parallelize
   only in isolated worktrees with disjoint files, commands, generated output, package-manager, and
   runtime state. Inspect every hunk; make only mechanical conflict/format corrections directly.
6. Add tests distinguishing requested behavior from prior behavior; demonstrate a bug regression
   against pre-fix behavior when practical. Run focused checks, then justified broader checks. Record
   exact commands/results; diagnose failures.
7. Before dependent work consumes an independently reviewable packet, freeze it and use a fresh
   non-author packet reviewer with contract, proof artifact, complete diff, consumers, and evidence—
   not writer rationale. Resolve material findings. A one-packet change proceeds to final review.
8. After any interface-affecting edit, re-evaluate the dependency/change-impact graph, consumers, packet
   order, and proof obligations. Return any judgment-changing deviation to scope.

## 6. Verify and review the exact candidate

Run deterministic acceptance checks after integration. Add a fresh integration verifier only for a
new boundary or proof obligation not covered by packet evidence. For review-only work, skip all
implementation gates and use the supplied entry contract.

Freeze the task manifest and route final review. Always use one fresh, non-author, read-only
whole-diff reviewer; use two when the topology requires. Give each the raw request, contract, intended
base, exact task manifest, complete task-only diff, consumers, and proof obligations—not author
conclusions, claimed success, or another report. Do not give them the author's conclusions. One reviewer covers both lenses; two split them:

- **Contract/simplicity:** derive behavior without author rationale; attack scope creep, unexplained
  hunks, needless machinery, and missed reuse.
- **Correctness/integration/proof:** seek the strongest failure across callers, state, errors, partial
  failure, compatibility, and test quality; include security, concurrency, data, and performance only
  when material.

Add a specialist only for an exact elevated risk or conflict. Each reviewer inspects every relevant
hunk/consumer, runs or inspects the smallest decisive checks, and returns material findings as
`pass`, `fail`, or `unverified`. Collect all routed reports before reconciliation.

Reproduce every finding. For a review-only request, do not edit, spawn a writer, or mutate repository or remote state; return findings and proving checks. In a full workflow, correct through a writer and
rerun decisive checks. Any task-owned change creates a new manifest, invalidates all routed reviewer verdicts, and reruns the full applicable review topology on the corrected fingerprint. Mechanical
checks cannot bypass final non-author whole-diff review.

Declare readiness only when every criterion has direct passing evidence checked by a non-author,
the final candidate state—not an earlier patch—was reviewed, all relevant checks pass, and no
unexplained hunk, material dissent, or unexpected worktree change remains.

Stop here for a review-only request. Return findings first and list residual validation gaps.

## 7. Deliver the reviewed PR

1. Deterministically verify task-manifest equality, unchanged ambient manifest, complete review
   evidence, no dissent, repository/origin, authentication, base, issue branch, final diff, and checks.
   If ancestry, ownership, PR identity, or evidence remains ambiguous, use a fresh readiness auditor;
   `fail` or `unverified` blocks delivery.
2. Commit only request-owned files with a concise issue-bearing message; do not amend unless asked.
   Prove each committed task path's content/mode and each task-untracked disposition equals the
   reviewed task manifest; separately prove all ambient staged, unstaged, and untracked paths unchanged. Verify ancestry and exact
   `HEAD`; any mismatch invalidates review.
3. Push normally. Resolve the exact head branch before creating a PR. Reuse one matching open PR;
   stop on duplicates or mismatches.
4. Create or update one ready-for-review PR with Summary, Changes, exact Verification, Adversarial
   review, and Linear issue. Re-read it; verify repository, base, head branch/commit, open state, and
   non-draft readiness. Never claim unobserved CI, approval, merge, or deployment state.
5. For Linear-backed work, post and re-read one `## Bonaparte · Delivery` comment with PR, branch,
   full commit, outcome, exact validation, review, resolved disagreement, and remaining conditions.

## Stop and report

Stop instead of manufacturing convergence when required subagents are unavailable; RCA is missing;
material disagreement survives the bounded discriminator; a user/product choice is missing; scope
would widen; proof is unverified; user work is at risk; corrections oscillate; or the exact final
candidate lacks non-author review. Never publish or claim readiness before all gates pass.

Lead the completion report with outcome. Include issue, branch/full commit, PR, delivered behavior,
exact validation, non-author review, evidence resolving disagreements, residual dissent or unverified
gaps, and remaining conditions. Do not expose hidden reasoning, identities, transcripts, or tool logs.
