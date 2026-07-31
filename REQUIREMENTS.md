# Tweed Requirements Specification

Status: Draft v0.2
Last updated: 2026-07-31

## 1. Purpose

Tweed is a personal, Linear-native system for delivering software changes through aggressive, adversarial use of agents.

Every requested change maps to one canonical Linear ticket. Agents may be numerous, short-lived, replaced, or run in parallel. The ticket, decisions, commits, artifacts, findings, and verification evidence are durable.

The required lifecycle is:

```text
Request
  → adversarial discovery
  → frozen Linear contract
  → parallel implementation
  → serial integration
  → adversarial review
  → bounded repair
  → verified completion
```

This document defines how that lifecycle behaves. It intentionally does not prescribe an interface, application layout, agent vendor, model, frontend framework, backend framework, or transport protocol.

## 2. Goals

The system must:

- Turn an incomplete change request into a complete, evidence-backed Linear ticket.
- Use independent agents with competing objectives during discovery and review.
- Ask the user only questions that materially affect the contract.
- Make the canonical ticket sufficient for a fresh implementation agent to begin without prior conversation history.
- Execute independent implementation packages in parallel without unsafe shared writes.
- Integrate implementation outputs deterministically.
- Review the integrated result for scope, simplicity, correctness, robustness, and verification quality.
- Repair evidence-backed defects and reverify affected behavior.
- Keep persistent project and coordinator contexts free from raw agent execution noise.
- Preserve enough provenance and evidence to audit every important decision and completion claim.
- Minimize routine supervision while stopping at genuine decision, safety, or correctness boundaries.

## 3. Non-Goals

The initial system does not need to define or provide:

- A particular user interface.
- A consumer project-management experience.
- A visual workflow builder.
- Arbitrary user-authored agent graphs.
- A prompt editor.
- A particular agent or model provider.
- A replacement for Git, Linear, testing tools, or deployment systems.
- Automatic scope expansion based on reviewer suggestions.
- Unbounded autonomous repair.
- Raw agent transcripts inside the canonical ticket.

## 4. Core Invariants

### 4.1 One request, one canonical ticket

Every independently deliverable change has one canonical Linear ticket. Related, independently shippable work may use linked child tickets, but decisions and scope must not be duplicated inconsistently.

### 4.2 Linear contains decision-relevant context

The canonical ticket contains:

- Outcome.
- Scope and non-goals.
- Verified current behavior.
- Assumptions.
- Decisions and rationale.
- Acceptance criteria.
- Implementation plan.
- Work packages and dependencies.
- Risks and safeguards.
- Validation plan.
- Execution snapshot.
- Known limitations and follow-ups.

Linear must not become a transcript landfill. Raw exploration, tool output, internal debates, superseded drafts, and verbose logs remain in linked audit storage.

### 4.3 One Ticket Steward writes the contract

Only one phase coordinator, called the **Ticket Steward**, may modify the canonical ticket description or authoritative stage state at a time.

Discovery agents, implementation agents, reviewers, and repair agents return structured packets to the relevant coordinator. They do not independently rewrite the canonical contract.

### 4.4 Agents are disposable

The system must survive agent failure, replacement, retry, or context loss. Durable state belongs to:

- Ticket revisions.
- Questions and answers.
- Decisions.
- Work packets.
- Branches and commits.
- Artifacts.
- Findings.
- Test and verification evidence.
- Stage receipts.

### 4.5 History is not context

Full execution history remains inspectable, but downstream agents receive only the frozen contract, required artifacts, accepted decisions, and relevant evidence.

### 4.6 Evidence outranks self-report

An agent stating that work is complete or tests passed is not sufficient. Completion and verification require evidence tied to the exact integrated revision and environment.

### 4.7 Scope changes require contract changes

Agents must not silently reinterpret or expand the ticket. Material changes to behavior, interfaces, safety, acceptance criteria, or work-package boundaries require a new contract revision and invalidation of affected work.

## 5. Linear Lifecycle

The system uses the following logical states. These may map to native Linear states, labels, or another configuration, but their meanings are fixed.

| State | Meaning |
|---|---|
| Discovery | Independent agents are gathering evidence and challenging the request. |
| Needs You | A material decision or permission requires user input. |
| Ready | The ticket is a complete and frozen implementation contract. |
| In Progress | Implementation packages are running or integrating. |
| In Review | The integrated candidate is undergoing independent review. |
| Repairing | Accepted blocker or must-fix findings are being corrected. |
| Ready to Merge | The candidate passed the configured completion gate and awaits an optional delivery action. |
| Done | The delivery boundary declared by the ticket has been reached. |
| Failed | Execution terminated without satisfying the contract. |
| Canceled | The user or policy intentionally stopped the change. |
| Stale | The contract or implementation is invalidated by relevant repository or decision changes. |

Code complete, merged, and deployed are distinct milestones. Each ticket declares which one counts as Done.

## 6. Phase 1: Request Intake

### 6.1 Initial ticket

When a change is requested, the system creates or identifies one Linear ticket and records:

- The original request without reinterpretation.
- Intended outcome, if known.
- Repository and planning base revision.
- Known constraints.
- Initial assumptions.
- Discovery status.
- Any immediately blocking question.

### 6.2 Frozen discovery input

All initial discovery agents receive the same request, project rules, and repository revision. They must work independently before seeing other agents' conclusions.

## 7. Phase 2: Adversarial Discovery

### 7.1 Independent discovery agents

The default discovery roles are:

- **Context mapper:** existing behavior, architecture, conventions, related code, issues, and documentation.
- **Requirements analyst:** intended behavior, missing requirements, ambiguities, and user-visible consequences.
- **Minimalist:** smallest safe change, avoidable complexity, and likely scope creep.
- **Failure hunter:** edge cases, concurrency, data safety, compatibility, rollback, and operational failure.
- **Implementation planner:** feasible decomposition, dependencies, ownership, and integration order.
- **Test designer:** executable acceptance criteria and verification strategy.

Agents must distinguish facts, assumptions, proposals, questions, and follow-ups.

### 7.2 Discovery return packet

Each discovery agent returns a bounded structure equivalent to:

```yaml
findings:
  - claim: string
    evidence: reference
    implication: string
    confidence: high | medium | low

proposals:
  - option: string
    benefit: string
    cost: string
    affected_scope: string

questions:
  - decision_required: string
    options: [string]
    recommended_default: string | null
    consequences: [string]

follow_ups:
  - independently useful but out-of-scope work
```

A statement without repository, user, issue, documentation, test, or runtime evidence is an assumption rather than a fact.

### 7.3 Cross-critique

A fresh adversarial group receives structured discovery packets, not raw discovery transcripts.

The default critique roles are:

- Scope critic.
- Completeness critic.
- Feasibility critic.
- Robustness critic.
- Testability critic.

The default is one critique round. A second round is allowed only for an unresolved material contradiction.

### 7.4 Question synthesis

The Ticket Steward deduplicates questions and applies this order:

1. Answer from verified project facts when possible.
2. Apply an accepted project rule when applicable.
3. Infer a reversible implementation detail and record it as an assumption when safe.
4. Ask the user only if the answer changes behavior, scope, a public interface, security, data safety, an irreversible action, significant cost, or architectural direction.
5. Move optional improvements to Follow-ups.

Each user question must include:

- The exact decision required.
- Why work is blocked or meaningfully affected.
- Available options.
- A recommendation when evidence supports one.
- Consequences of each option.
- Whether the answer is task-local or proposed as a reusable project rule.

The user response is normalized into a decision. Downstream agents receive the normalized decision, not the clarification conversation.

### 7.5 Contract synthesis

A fresh planner receives only:

- Original outcome.
- Verified findings.
- Explicit assumptions.
- Accepted decisions.
- Scope and non-goals.
- Constraints.
- Relevant evidence.

It creates a readable, executable contract and bounded work packages.

### 7.6 Red-team readiness review

Before Ready, fresh agents must challenge the completed ticket:

- Can the outcome or plan be made smaller?
- Is any requirement ambiguous or untestable?
- Does the plan contradict repository evidence?
- Are work packages truly independent?
- Are risks, rollback, and compatibility covered?
- Has an attractive improvement escaped the agreed scope?
- Would a fresh implementation agent require hidden context?

## 8. Canonical Ticket Contract

The authoritative Linear description must follow this structure.

```markdown
# Outcome

[Observable result and why it matters.]

## Scope

- [Required behavior]

## Non-goals

- [Explicit exclusion or deferred improvement]

## Current behavior and evidence

- **Fact:** [Current behavior]
  - Evidence: [repository, issue, document, test, or runtime reference]
- **Assumption:** [Explicitly unverified assumption]

## Decisions

- **D1 — [Decision]**
  - Reason: [Rationale]
  - Source: [User, accepted rule, or evidence]
  - Rejected alternative: [Alternative and reason]

## Acceptance criteria

- [ ] AC-1: [Binary observable condition]
- [ ] AC-2: [Failure or edge-case behavior]
- [ ] AC-3: [Compatibility or migration outcome]
- [ ] AC-4: [Required verification]

## Implementation plan

### WP1 — [Outcome]

- Ownership: [Subsystem or files]
- Depends on: [Packages or none]
- Parallel with: [Packages or none]
- Work:
  - [Concrete change]
- Done when: [Observable condition]
- Validate with: [Test or evidence]

### Integration order

1. [Package or checkpoint]
2. [Package or checkpoint]
3. Clean-checkout verification

## Risks and safeguards

| Risk | Detection | Mitigation or rollback |
|---|---|---|
| [Material risk] | [How detected] | [Response] |

## Validation plan

- Unit:
- Integration:
- Regression:
- Runtime or manual:
- Clean-checkout final verification:

## Follow-ups

- [Useful improvement deliberately excluded from this ticket]

## Execution snapshot

- Repository:
- Planning base revision:
- Contract revision:
- Blocking questions: 0
- Delivery boundary:
```

### 8.1 Ticket size and decomposition

The ticket must remain readable. As a default:

- Use one outcome paragraph.
- Prefer five to seven acceptance criteria.
- Prefer three to six work packages.
- Include only material risks.
- Consider decomposition when the contract exceeds roughly 1,200 words.

Use linked child tickets only for independently mergeable, long-lived, or cross-repository packages. Child tickets reference parent decisions instead of copying them.

### 8.2 Ticket revisions

Every Ready contract records a revision and planning base commit.

Before implementation:

- Continue when repository changes are unrelated to contract assumptions and affected surfaces.
- Run targeted rediscovery when relevant areas changed.
- Increment the contract revision when decisions, scope, interfaces, or acceptance criteria change.
- Invalidate only affected work packets and evidence where possible.
- Never silently implement a stale contract.

## 9. Ready Gate

A ticket may enter Ready only when all are true:

- The outcome is observable.
- Scope and non-goals are explicit.
- Material claims have evidence or are labeled assumptions.
- No blocking user decision remains.
- Acceptance criteria are executable.
- Work packages have clear ownership and dependencies.
- Proposed parallel work is collision-safe.
- Material failure modes have detection and mitigation.
- Migrations or destructive work include rollback guidance.
- Repository and planning base revision are recorded.
- The ticket remains readable.
- A fresh implementation agent can start without discovery history.

Readiness is Boolean, not a confidence score. Any failed requirement keeps the ticket in Discovery or Needs You.

## 10. Phase 3: Implementation Preflight

Starting implementation creates a fresh coordinator from:

```text
Frozen ticket revision
+ pinned repository revision
+ accepted project rules
```

It does not receive discovery transcripts.

Before code changes, independent agents perform:

- **Dependency mapping:** convert the ticket plan into executable dependency waves.
- **Collision analysis:** identify overlapping files, interfaces, migrations, generated output, and runtime state.
- **Scope minimization:** challenge unnecessary packages or abstractions without changing ticket scope.

The coordinator may simplify implementation boundaries. It may not change requirements or acceptance criteria without a contract revision.

## 11. Phase 4: Parallel Implementation

### 11.1 Work packets

Every writer receives a bounded packet equivalent to:

```yaml
packet_id: WP-2
outcome: string
acceptance_criteria: [AC-2, AC-4]
depends_on: [WP-1]
owned_surfaces:
  - path or subsystem
interfaces:
  consumes: [contract]
  produces: [contract]
out_of_scope:
  - excluded change
required_tests:
  - required verification
allowed_actions:
  - bounded action
return:
  - commit
  - changes
  - acceptance criteria addressed
  - test evidence
  - assumptions
  - deviations
  - risks
```

Agents receive the frozen contract, their work packet, relevant project rules, and required artifacts. They do not receive other agents' transcripts.

Implementation agents may use private subagents. Child results must return as bounded packets.

### 11.2 Parallelism and worktrees

Use one task integration branch per ticket and one temporary worktree or child branch per concurrent writer.

Required rules:

- Read-only agents may share immutable snapshots.
- Independent packets run in parallel.
- Dependencies run in waves.
- No two agents write the same branch concurrently.
- Overlapping writers are serialized or isolated as competing implementations.
- High-risk packages may use competing isolated attempts.
- A separate selector compares competing attempts using contract criteria.
- Child branches integrate serially into the task branch.
- Interface tests run after relevant integrations.
- Final verification runs against a clean checkout of the integrated revision.
- A worktree is cleaned only after commits, patches, packets, and evidence are durable.

The default maximum is three concurrent writers. Read-only agents may be used more broadly.

### 11.3 Implementation questions

Questions are durable ticket-scoped objects. A question must include:

- Question identifier.
- Work packet.
- Blocking scope.
- Reason.
- Options.
- Recommendation when available.
- Impact.
- Safe default, if the contract explicitly authorizes one.

Unaffected packages continue when possible.

After an answer:

- Normalize it into a decision.
- Increment the contract revision when required.
- Notify only affected packets.
- Pause and regenerate stale packets when shared scope or interfaces changed.

### 11.4 Implementation integration packet

Each completed worker returns:

- Packet identifier and status.
- Commit or patch reference.
- Acceptance criteria addressed.
- Change summary.
- Test commands and outcomes.
- Assumptions.
- Deviations.
- Known risks.

The integration coordinator receives commits, packets, and evidence rather than worker conversations.

### 11.5 Implementation completion gate

Implementation is ready for review only when:

- Every work packet is integrated.
- Every acceptance criterion maps to an integrated change or required evidence.
- Required tests pass on the integrated revision.
- No blocking question remains.
- No unapproved scope deviation remains.
- The diff contains no unexplained unrelated changes or placeholders.
- Contract amendments are reflected in Linear.
- The review bundle is complete and reproducible.

An individual worker saying “done” never completes the implementation phase.

## 12. Phase 5: Independent Adversarial Review

### 12.1 Frozen review input

Review begins against a frozen delivery candidate containing:

- Frozen ticket revision.
- Base and candidate commit identifiers.
- Integrated diff.
- Work-package-to-commit manifest.
- Acceptance criteria.
- Test commands, environment, results, and evidence.
- Approved deviations.
- Relevant project rules.

Reviewers must not receive implementation explanations or transcripts.

### 12.2 Blind review lanes

Three reviewers submit independently before seeing peer results.

#### Scope and simplicity

- Map acceptance criteria to the diff and evidence.
- Detect missing requirements and unauthorized scope.
- Challenge new abstractions, dependencies, configuration, and indirection.
- Suggest concrete deletion or consolidation.

#### Correctness and robustness

- Search for logic errors, races, malformed input, partial failure, retries, cleanup, rollback, data corruption, and compatibility problems.
- Challenge plan assumptions against the implementation.

#### Verification and integration

- Determine whether tests actually prove the acceptance criteria.
- Find missing regression and boundary coverage.
- Verify interfaces between parallel packages.
- Verify the integrated result from a clean checkout.

Triggered specialists join only when required by the ticket or diff, such as security, privacy, authentication, migrations, data integrity, performance, payments, or destructive effects.

### 12.3 Finding contract

Every finding must contain:

```yaml
category: scope | simplicity | correctness | robustness | security | testing | integration
severity: blocker | must_fix | advisory
claim: one falsifiable statement
evidence: concrete reference or reproduction
failure_mode: observable consequence
contract_link: acceptance criterion, non-goal, or project rule
minimal_remedy: smallest safe correction
confidence: high | medium | low
```

Reject findings that are:

- Purely stylistic.
- Unrelated to the ticket.
- Unsupported by evidence or a credible execution path.
- General best-practice preferences without a concrete consequence.

Severity means:

- **Blocker:** acceptance, security, data-loss, or serious regression failure.
- **Must-fix:** credible material defect or missing required verification.
- **Advisory:** worthwhile simplification or improvement not required for safe delivery.

Advisory findings never reopen or expand a passing ticket automatically.

### 12.4 Finding synthesis

A fresh synthesizer:

1. Clusters findings by root cause and observable failure.
2. Combines evidence while preserving reviewer provenance.
3. Recalibrates severity using the fixed rubric.
4. Records accepted, rejected, contested, and advisory findings.
5. Does not invent new findings.

Contested blockers are not decided by majority vote. A targeted adjudicator attempts to falsify competing claims through evidence or focused tests. Unresolved material uncertainty becomes one narrow Needs You question.

## 13. Phase 6: Repair and Reverification

Accepted blocker and must-fix findings become narrow repair packets containing:

- Finding and evidence.
- Expected corrected behavior.
- Relevant acceptance criterion.
- Permitted files or subsystem.
- Required regression test.
- Instruction to make the smallest safe change.

Repairs run in parallel only when ownership is disjoint. Overlapping repairs are serialized.

After every repair:

1. Reproduce the original failure when feasible.
2. Run the targeted regression test.
3. Run impacted suites.
4. Integrate repairs serially.
5. Run acceptance checks against the new final revision from a clean checkout.
6. Re-run affected review lanes.
7. Run a lightweight scope check.

Any code change invalidates affected verification evidence.

### 13.1 Bounded loops

Default limits are:

- Two repair attempts per finding cluster.
- Three integrated review rounds per ticket.
- Advisory findings do not reopen work.
- Out-of-scope discoveries become follow-up proposals.
- The same unresolved failure twice becomes Needs You.
- A materially defective contract returns to Discovery as a new revision.

Exhausting the limit does not make the ticket complete. The system preserves evidence and asks for the smallest necessary user decision.

## 14. Completion Gate

A ticket is verified only when:

- Every acceptance criterion has current evidence against the exact final revision.
- No accepted blocker or must-fix finding remains unresolved.
- Required specialist reviews passed.
- Integration and clean-checkout verification passed.
- Repairs were reverified and affected surfaces were re-reviewed.
- Unauthorized scope changes were removed or explicitly approved.
- Deviations and known limitations are recorded.
- Branch, commit, diff, tests, review findings, and evidence are linked.
- The declared delivery boundary has been reached.

The final stage receipt must summarize:

- Outcome delivered.
- Final revision.
- Acceptance-criteria evidence.
- Review result.
- Repairs performed.
- Known limitations.
- Follow-up proposals.
- Delivery state: code complete, merged, or deployed.

## 15. Context Isolation

Every phase uses a separate coordinator context:

```text
Persistent project
├── Discovery coordinator
│   └── discovery and critique agents
├── Implementation coordinator
│   └── implementation and integration agents
└── Review coordinator
    └── review, adjudication, and repair agents
```

The canonical ticket is the primary phase handoff. Coordinators do not inherit prior phase transcripts.

The persistent project context contains only stable information:

- Original request.
- Linear ticket reference.
- Current frozen contract revision.
- Accepted project decisions.
- Final verified result.
- Artifact and evidence references.

Parents receive structured child results. Prompts, tool calls, command logs, intermediate messages, rejected exploration, and private reasoning remain audit-only.

## 16. Audit and Linear Update Policy

The canonical issue description is the current normalized contract. Comments form a concise append-only milestone log.

The coordinator writes comments only for meaningful events such as:

- Discovery completed and contract frozen.
- Implementation started.
- A material decision changed the contract.
- Implementation integrated.
- Review round completed.
- Repair round completed.
- Final verification completed.
- Execution failed, became stale, or needs user input.

Fine-grained agent activity remains outside Linear.

Every stage receipt must reference the relevant contract revision, repository revision, artifacts, and evidence.

## 17. Failure and Recovery Requirements

### Incomplete ticket

Return to Discovery. Do not allow implementation agents to invent missing product requirements while editing code.

### Worker crash or timeout

Resume or replace the worker from its durable packet, branch, commits, and recorded events.

### Duplicate result

Accept only the first valid completion for a packet or handle duplicates idempotently.

### Test failure

Create a targeted repair packet with evidence. Apply bounded retry rules.

### Integration conflict

Use a conflict-resolution agent with both work-packet contracts and the exact conflict. Escalate semantic ambiguity.

### Scope drift

Reject, trim, or require a contract amendment. Do not silently accept unrelated work.

### Stale base

Detect whether changed repository areas intersect the contract's assumptions or affected surfaces. Reconcile and rerun affected validation before continuing.

### Contract amendment

Increment the contract revision and invalidate only affected packets and evidence where possible.

### External side effect

Require explicit authorization, a durable intent record, and an idempotency key when the external system supports one.

### Cleanup

Preserve branches, patches, result packets, findings, and evidence before removing worktrees or temporary environments.

## 18. Personal Defaults

```yaml
effort: thorough

discovery:
  independent_scouts: 6
  critique_rounds: 1
  second_round_only_for_material_conflict: true
  readiness_review: required

implementation:
  max_concurrent_writers: 3
  isolated_worktree_per_writer: true
  dependency_waves: true
  serial_integration: true
  clean_checkout_verification: true

review:
  blind_reviewers:
    - scope_and_simplicity
    - correctness_and_robustness
    - verification_and_integration
  triggered_specialists: true
  max_review_rounds: 3
  max_repairs_per_finding: 2

questions:
  ask_only_when_decision_changing: true
  answer_from_verified_context_first: true
  route_to_originating_ticket: true
  task_local_by_default: true
  remember_project_rule: optional

linear:
  coordinator_only_writes: true
  comments_at_stage_gates_only: true
  raw_transcripts_excluded: true
```

## 19. System Acceptance Criteria

The system structure is acceptable when it can demonstrate that:

1. A vague request becomes one readable, evidence-backed Linear contract.
2. Independent discovery agents do not see each other's conclusions before submitting.
3. The system asks only deduplicated, material questions and records normalized decisions.
4. Implementation cannot start until the Boolean Ready gate passes.
5. Fresh implementation agents can work from the ticket without discovery transcripts.
6. Independent work packets can execute concurrently without shared-branch writes.
7. Integration is serialized and produces one reproducible candidate revision.
8. Blind reviewers independently evaluate scope, simplicity, robustness, bugs, and verification.
9. Only evidence-backed blockers and must-fix findings reopen implementation.
10. Repairs are narrowly scoped, bounded, reverified, and re-reviewed.
11. Every acceptance criterion traces to evidence for the exact final revision.
12. The persistent project context excludes raw agent execution history.
13. Linear remains a readable contract and milestone record rather than a raw activity log.
14. Failure, retry, staleness, and cleanup preserve durable work and evidence.
15. The user is interrupted only when the system cannot safely proceed under the frozen contract.

## 20. Operating Principle

> The Linear ticket is the frozen outcome contract. Independent adversarial agent swarms discover, implement, and attack it. Only structured decisions, artifacts, evidence, and results cross phase boundaries, and the user is interrupted only for decisions the system cannot safely make.
