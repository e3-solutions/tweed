# Understand intent and route the work

Use this front end for new, ambiguous, or substantial tasks. Understand what the
user wants before optimizing how to implement it. Reuse the conversation, accepted
decisions, repository guidance, and retained evidence. A clear Quick edit needs a
brief goal and focused check, not an interview or a separate specification.

## Build the smallest useful intent brief

Resolve these questions at the depth the task needs:

- Who uses the result, what problem does it solve, and what observable outcome
  makes it useful? Give a concrete before/after example when wording is ambiguous.
- What must happen, what must never happen, and which nearby behaviors must remain?
- What constraints govern interfaces, data, compatibility, performance, cost,
  privacy, deployment, and rollback? Include only constraints relevant to this task.
- What is deliberately outside scope, what authority is already granted, and which
  decisions remain unresolved?
- Which facts were checked, which statements are assumptions, and what evidence
  will distinguish a working result from a plausible implementation?

Use existing glossary terms and architecture decisions when present. If a term has
several meanings, use a concrete scenario and check the implementation before
settling on one. Keep the brief proportional; do not create a glossary, long story
catalog, or architecture document unless the task needs it.

Separate discoverable facts from decisions. Inspect source, tests, documentation,
runtime receipts, and authorized services for facts instead of asking the user to
do that work. Ask concise, grouped questions when the remaining choice changes the
desired outcome, acceptance, consequential risk, or authority. Explain the effect
of each meaningful option. Preserve answers already given and existing
authorization; routine implementation choices remain with the owner.

Use the host's asynchronous question mechanism when available, with concise
options and a recommendation when evidence supports one. Word questions neutrally
so that agreement is not the default answer. Use
[question patterns](question-patterns.md) for scenarios, counterexamples and
tradeoffs. After an answer or a new
discovery, recompute the unresolved decision frontier and relevant readiness;
neither a question timeout nor a suggested default supplies a required answer.

When a consequential answer is required, hold work that depends on it and continue
independent discovery or preparation. Do not silently choose a product tradeoff
because the user has not replied. If assumptions are adequate for reversible work,
state them and proceed within scope. New evidence can reveal new unknowns: intake
does not establish that every question is resolved forever.

For Standard/Critical repository work, use the existing contract `intent` fields:
`goal`, `must_happen`, `must_not_happen`, `constraints`, `non_goals`,
`open_questions`, and `assumptions`. Connect desired behaviors to obligation IDs
and their checks. Reuse a suitable existing spec instead of duplicating it. A
read-only request without artifact authority keeps its brief in the response or
retained conversation. These instructions add no report fields or router runtime.

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

For a difficult bug, derive competing causes from source and observed evidence.
State the observable prediction of each live hypothesis and choose a targeted
probe that distinguishes them. Use the result to retire or refine the explanation;
do not apply a speculative fix just because one plausible story was generated.
[Question and solver patterns](question-patterns.md) give compact forms for
predictions, symptom-sensitive diagnostics, independent expected values, and
before/after checks on the original scenario.

Use [model routing](model-routing.md) throughout. Qualified lower-cost workers can
map source, extract known decisions, identify candidate ambiguities, and propose
acceptance cases. The owner resolves intent, checks completeness, verifies promoted
findings, and selects the route. Consequential decisions and required Critical
proof design/review use suitably capable independent actors. Use deterministic
enumeration directly when it answers the question; there is no fixed model ladder
or required agent count.

## Turn intent into observable slices

For each consequential requirement, name the behavior, the public interface or
boundary used to observe it, the expected outcome, and important failure cases.
Describe what the selected check catches and what it misses. A passing internal
mock cannot close a promised real persistence or external-service behavior.
Uncovered required behavior stays a gap rather than becoming an implicit exclusion.

Prefer a small behavior/check/change cycle over writing all imagined tests before
implementation. Use independently derived expected values and existing useful
interfaces. Tests should survive equivalent correct implementations. When using a
forced-red mutation, show that it corresponds to the reported symptom and fails
by the relevant assertion, not by syntax, import, or runner failure. Keep the real
before/after diagnostic where available; mutation sensitivity alone is not proof
that the original incident occurred. See [evidence](evidence.md) for capture.

Separate implementation scheduling from logical proof. Edit ownership, integration
order, and worktree constraints can block a worker without implying `depends_on`
between its claims. Use that field only for actual proof prerequisites. Parallelize
ready independent scopes, serialize shared writes, and verify the integrated tree.
Use [complex tasks](complex-tasks.md) for dependency invalidation and recovery.

## Review, finish, and learn

Keep two review judgments visible: does the result satisfy the intended behaviors,
and does it follow the applicable repository standards? Standards compliance cannot
compensate for a missing requirement. Pin the relevant comparison and intent;
different task scopes may require different diffs. Independent reviewers can cover
distinct questions in parallel when worthwhile; do not duplicate agents simply to
populate categories. Preserve the required separate Critical proof-design and
adversarial-review roles and their provenance.

The owner checks requirement coverage, consequential decisions, current proof,
remaining misses, and actual delivery before completion. The CLI checks evidence
consistency and recorded gates; it does not understand whether an open question or
test omission violates the user's goal. Do not claim semantic coverage from a
passing suite or `validate --require-complete` alone.

After a discovery changes intent or scope, update the contract and re-evaluate the
affected proof and review. After a handoff or compaction, recover the accepted
brief, authority, source revision, evidence location, unresolved choices and next
action, then recompute readiness rather than trusting summary pass labels. Retain
useful observed lessons: prefer an existing deterministic check for mechanical
failures and a concise decision rule for judgment failures. Environment changes
and external effects keep their own authorization.

This is an authored adaptation of fundamentals in
[Matt Pocock's skills](https://github.com/mattpocock/skills/tree/49dd158d1076134a641b33efb035946536778336),
especially intent clarification, specs, vertical slices, TDD, separate review
axes, and handoff. Their operational approval, tracker, installation, and commit
rules are not task authorization. This guidance has not established an improvement
in model accuracy, autonomous completion, or verified-outcome cost.
