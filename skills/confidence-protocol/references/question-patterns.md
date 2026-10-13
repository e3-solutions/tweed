# Question and solver patterns

Use these patterns when a task needs a user decision, a diagnosis, a test oracle,
or a design comparison. They support [intent flows](intent-flows.md) and
[model routing](model-routing.md). They add no mode, report field, dispatcher,
model ladder or required step. A clear Quick edit uses none of them unless one
removes real doubt.

## Separate facts from choices

- **Facts** cover current source, tests, runtime receipts, documentation, prices and
  account availability. Find them yourself or through a bounded worker. Check every
  fact you promote.
- **Choices** cover product tradeoffs, acceptable risk, scope, cost and
  source-exposure authority, and anything else the user owns. Ask about a choice
  only when its answer changes the outcome, acceptance, consequential risk or
  authority.
- **Mixed.** When a choice depends on an unknown fact, resolve the fact first and ask
  the choice afterwards. Ask independent choices now.

A missing reply, timeout or suggested default does not settle a consequential
choice. Continue independent work, and hold only the work that depends on the answer.

## Ask a practical conditional question

Group the choices that can be answered now into one message. Use only the parts
that make the decision easier; this is not a mandatory five-part question form:

1. **Decision.** One idea, in the user's terms.
2. **Why it matters.** What changes in behavior, acceptance, risk or cost.
3. **Options.** For each option, a concrete scenario showing its result and a
   counterexample where it does worse.
4. **Facts and assumptions.** Label which statements were checked and which are assumed.
5. **Recommendation, only if evidence supports one.** Give the reason and the evidence
   that would change it. Omit it when the choice is a genuine preference.

Word each question neutrally. Do not phrase it so that answering 'yes' adopts the
recommendation. Ask the user to name an option or describe another. When the right
answer depends on a situation the user knows, use a conditional form: 'If X happens,
should the result be A or B?'

Illustrative example (the file reference is hypothetical):

> **Retrying an upload after a timeout.** This decides whether a user can end up
> with a duplicate file.
> - A, retry automatically. On a flaky network the upload finishes with no user
>   action. If the first attempt actually landed, the user gets two copies unless
>   the server deduplicates. Server deduplication is an assumption; it has not been
>   checked.
> - B, report an uncertain outcome and check upload status before retrying. A user
>   on a weak connection waits longer; a blind manual retry could still duplicate.
> Checked: the upload endpoint takes no idempotency key (`api/upload.ts:42`).
> Recommendation: B until deduplication exists, because duplicates are hard to undo.
> Which option do you want, or would you prefer another?

After each answer or new discovery, recompute which questions can now be answered.
New evidence can open new questions.

## Solver patterns

Use a pattern when it changes the next action. These patterns are tools, not gates.

**Falsifiable predictions.** For a nontrivial bug or design claim, list the live
explanations that source and observations support. For each one, state what a
specific probe would show if it were true and what result would retire it. Run the
cheapest probe that separates them, changing one variable at a time. A story
without a prediction is not yet a hypothesis.

**Symptom-sensitive diagnostic.** Before theorizing, get one runnable check that
reproduces the reported symptom: the exact error, wrong value or timing, not a
nearby failure. Make the check deterministic. For flaky failures, report the
observed reproduction rate instead. If no check can be built, record what was tried
and what access or artifact would help. Redact secrets in any output you show.

**Independent expected values.** Derive expected outputs from the spec, a worked
example, a reference calculation or previously recorded behavior. Never copy the
output of the code under test. Note the derivation beside the assertion. A good test
passes for any correct implementation and fails for the reported defect.

**Abstraction deletion, only when a layer is in question.** Imagine removing the
layer. If callers would absorb no new complexity, the layer is a pass-through. If
complexity would reappear at several callers, the layer earns its place. A seam with
one implementation and nothing that varies across it is usually speculative.

**Contrasting designs, only for consequential interface or architecture choices.**
Use this when the first design is not clearly right. Produce two or three
deliberately different designs, for example the smallest interface, an easy default
for the common caller, and explicit adapters. Give each design a usage example and
its weak spot. Compare them on caller effort, where change concentrates, and
testability through the public interface. Skip this pattern for local fixes.

**Original scenario before and after.** After a fix, rerun both the original
unreduced scenario and the minimized regression check, and record both outcomes. A
forced-red mutation shows that a check is sensitive. It does not show that the
original incident occurred, so keep the real before result where available.

## Deterministic checks stay deterministic

Completeness and negative claims ('all callers', 'no other writer') need a stated
search scope and method. The owner reruns that search before relying on the claim.
Run cheap enumerations directly and give workers the resulting set to classify. A
worker's positive citations cannot show that nothing was missed.

## Routing these patterns

Lower-cost workers can enumerate hypotheses, draft predictions, propose tests and
expected values, or sketch contrasting designs. The owner checks their output before
promoting any of it. Route by consequence and checkability, not by model name.

A user's route preference sets intent. It is not evidence of accuracy or cost.

A cheap classification of a change as low-risk does not replace the required
Critical roles. Critical work still needs independent proof design before
implementation and separate adversarial review afterwards, each with its own origin
and context.

## Compact worker prompt

```
Role: <discovery | test proposal | isolated edit | proof design | adversarial review>
Question: <one falsifiable question>
Source scope: <packet path or files@revision>; use nothing outside it
Tool boundary: <what the harness actually enforces>
Owned files (edits only): <list>; other agents may be editing; send any edit
  outside this list to the owner
Evidence supplied: <requirements, raw logs, enumerated set>
Return: findings with source locations, each labeled as observed fact, candidate
  explanation, proposed check or missing information; expected values with their
  derivation; gaps
Stop when: <condition>, or when the budget ends; then report partial results
Do not: endorse a proposed answer, fill gaps from memory, or act outside the boundary
```

## Owner verification skeleton

```
Route:        requested model/effort | observed model | harness version | boundary checked
Terminal:     exit status | result status | nested tool errors | timeout
Findings:     each promoted item -> source read at revision | check run | outcome
Completeness: scope and method rerun by owner | remaining gaps
Oracles:      expected values derived independently of the implementation?
Diagnostic:   red on the original symptom | green after | original scenario rerun
Critical:     proof-design origin | adversarial-review origin | separate contexts
Rejected:     unverified or contradicted findings, each with a reason
```

## Limits

This reference paraphrases ideas from [Matt Pocock's pinned skills](https://github.com/mattpocock/skills/tree/49dd158d1076134a641b33efb035946536778336) (grilling, domain
modeling, diagnosing bugs, codebase design, questionnaires) and adapts them to
Confidence Protocol evidence rules. Some of their operational rules are
deliberately not adopted: wording questions so that 'yes' accepts the
recommendation, fixed hypothesis counts, required sub-agent counts and the
opinionated-recommendation requirement. The source adaptation alone does not show improved accuracy, fewer user
interventions or lower cost. Keep controlled task outcomes separate from this
reference's instruction checks.
