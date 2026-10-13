# Understand intent and route the work

Use this front end for new, ambiguous, or substantial tasks. Understand what the
user wants before optimizing how to implement it. A clear Quick edit needs a
brief goal and focused check, not an interview or a separate specification.

## Recover before asking

Start from what is already decided: the conversation, an existing contract's
`intent`, accepted specs or architecture decisions, repository guidance, and
retained evidence. Do not re-ask a settled decision; restate it in the brief so a
wrong recovery is visible. Use existing glossary terms; when a term has several
meanings, settle it with a concrete scenario checked against the implementation.
Then resolve the rest at the depth the task needs:

- Who uses the result, what problem does it solve, and what observable outcome
  makes it useful? Give a concrete before/after example when wording is ambiguous.
- What must happen, what must never happen, and which nearby behaviors must remain?
- Which constraints on interfaces, data, compatibility, performance, cost,
  privacy, deployment, and rollback apply to this task?
- What is outside scope, what authority is already granted, and which decisions
  remain unresolved?
- Which facts were checked, which statements are assumptions, and what evidence
  will distinguish a working result from a plausible implementation?

Separate discoverable facts from decisions. Inspect source, tests, documentation,
runtime receipts, and authorized services for facts instead of asking the user.
Ask about a choice only when its answer changes the outcome, acceptance,
consequential risk, or authority. Ask the current frontier in one grouped message:
choices whose prerequisites are settled, worded neutrally, with each option's
effect and a recommendation only when evidence supports one. Routine
implementation choices stay with the owner. Use
[question patterns](question-patterns.md) when a choice is hard to frame or a
diagnosis needs sharpening.

An answer settles only what it addresses. Who may perform an action does not
settle when it may happen, what it must wait for, or which later updates it
accepts. Before declaring readiness, check each remaining prerequisite of the
next dependent action: discover existing behavior, then ask if a consequential
gate is still open. Do not infer the rest of a decision from one answer.

Hold only work that depends on an unanswered consequential choice, and continue
independent discovery or preparation. A timeout or suggested default does not
supply the answer. If assumptions are adequate for reversible work, state them and
proceed within scope. After each answer or discovery, recompute the open frontier;
new evidence can reopen a question.

## Write a concise contract

For Standard/Critical repository work, record the brief in the existing contract
`intent` fields: `goal`, `must_happen`, `must_not_happen`, `constraints`,
`non_goals`, `open_questions`, and `assumptions`. Connect required behaviors to
obligation IDs and their checks. Name the interfaces involved and end with the
end-to-end check that shows the outcome works. Reuse a suitable existing spec
instead of duplicating it. A read-only request without artifact authority keeps
its brief in the response. Do not create a glossary, story catalog, or architecture
document unless the task needs it.

## Choose the flow and proof mode separately

Choose by the user's actual task and remaining uncertainty. Apply [modes](modes.md)
and [task profiles](task-profiles.md) to its consequences; a feature or research
label does not lower a Critical trust or persistence boundary.

| Task | Useful sequence | Evidence that changes the next action |
| --- | --- | --- |
| Clear Quick edit | Brief goal → direct change → smallest adequate check. | Inspect the actual change; add no test or agent ceremony when it adds no value. |
| Research or design question | Decision/question → primary sources → competing explanations or a bounded prototype → supported answer. | Cite checked facts, separate inference, retain unknowns; a throwaway prototype does not certify production behavior. |
| Bug | Expected/actual behavior → executed reproduction → reduction and hypothesis → focused repair → original scenario and nearby regressions. | Show the diagnostic detects the symptom and that the repair removes it. |
| Feature or product | User outcome → acceptance examples and boundaries → useful vertical slice → implement/check → integrated behavior. | A slice exercises an observable path; partial failure, permissions and persistence need their actual boundary proof. |
| Refactor or architecture | Preserved public behavior → caller/dependency evidence → bounded simplification or justified expand–contract → compatibility proof. | A wide staged migration may need expansion, caller migration, and later contraction instead of pretending each edit is a complete feature. |
| Review or delivery | Requested source/diff and spec → requirements assessment and standards assessment → evidence, findings and authorized follow-up. | A review-only request produces a review; changes, commits, tracker writes and publication use their actual task authority. |

For a difficult bug, derive competing causes from source and observed evidence,
state what a targeted probe would show for each, and run the probe that separates
them. Do not apply a speculative fix because one plausible story was generated.

## Reuse existing components

A sequence above can run through a component that is already present: a
repository workflow (documented test, release or review command, task template),
or an installed skill such as a Matt Pocock or GSD skill. Resolve candidates from
what the repository guidance, the user, or the harness's skill list already
names; do not search for, install or update components. Use one only when it
serves the current task step. Read its entrypoint first: what it does, which
commands it runs, which files, trackers or commits it writes, and which agents it
dispatches. The contract's intent, proof requirements and granted authority stay
binding. Skip steps that need authority the task lacks or that would start a
second orchestration loop, and treat the component's success report as a claim
for the normal checks. When nothing relevant is available, or its entrypoint
cannot be read, follow the sequence above directly; no component is required.

## Execute to completion

For each consequential requirement, name the behavior, the public interface used
to observe it, the expected outcome, and important failure cases. State what the
selected check catches and misses. A passing internal mock cannot close a real
persistence or external-service promise; uncovered required behavior stays a gap.

Work in small behavior/check/change cycles. Use independently derived expected
values; tests should survive equivalent correct implementations. A forced-red
mutation must fail by the relevant assertion, and does not show that the original
incident occurred; keep the real before/after diagnostic where available. See
[evidence](evidence.md) for capture.

Carry authorized work through implementation, checks and repair without pausing
for routine confirmation. When the same failure survives two repairs without new
evidence, change the hypothesis, scope, or route, or report a precise blocker.
Use [model routing](model-routing.md) for delegation; use deterministic search
directly when it answers the question.

Separate implementation scheduling from logical proof. Edit ownership and
integration order can block a worker without implying `depends_on` between its
claims. Use that field only for actual proof prerequisites. Serialize shared
writes and verify the integrated tree. Use [complex tasks](complex-tasks.md) for
dependency invalidation and recovery.

## Review and finish

Keep two review judgments visible: does the result satisfy the intended behaviors,
and does it follow repository standards? Standards compliance cannot compensate
for a missing requirement. Pin the compared revision and intent. Ask reviewers for
findings that affect correctness or a stated requirement; treat other suggestions
as optional so review does not add speculative complexity. Reviewers can cover
distinct questions in parallel; do not duplicate agents to populate categories.
Preserve the required separate Critical proof-design and adversarial-review roles
and their provenance.

The CLI checks evidence consistency and recorded gates; it does not know whether
an open question or test omission violates the user's goal. A passing suite or
`validate --require-complete` alone does not establish semantic coverage.

After a discovery changes intent or scope, update the contract and re-evaluate the
affected proof and review. After a handoff or compaction, recover the accepted
brief, authority, source revision, evidence location, open choices and next
action from durable state, then recompute readiness rather than trusting summary
pass labels. Environment changes and external effects keep their own authorization.

This is an authored adaptation of fundamentals in
[Matt Pocock's skills](https://github.com/mattpocock/skills/tree/49dd158d1076134a641b33efb035946536778336)
(MIT), especially decision-frontier interviews, specs, vertical slices, TDD and
separate review axes. Their tracker, installation, and commit rules are not task
authorization. This guidance has not been shown to improve model accuracy,
autonomous completion, or verified-outcome cost.
