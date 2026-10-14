# Question and solver patterns

Load this only when a user choice is hard to frame or a diagnosis, test oracle or
design comparison needs sharpening. It supports [intent flows](intent-flows.md)
and adds no mode, report field, dispatcher or required step.

## Ask a choice the user can answer

Find facts yourself; ask the user only about choices they own. When a choice
depends on an unknown fact, resolve the fact first. Use only the parts that help:

1. **Decision** in the user's terms, and why it changes behavior, risk or cost.
2. **Options**, each with a concrete scenario where it does well and one where it
   does worse.
3. **Checked facts versus assumptions**, labeled.
4. **Recommendation** only when evidence supports one, with what would change it.

Word the question so that agreement is not the default: ask the user to name an
option or describe another. When the answer depends on a situation the user knows,
ask conditionally: "If X happens, should the result be A or B?"

> **Retrying an upload after a timeout** decides whether a user can end up with a
> duplicate file. A, retry automatically: no user action on a flaky network, but
> two copies if the first attempt landed and the server does not deduplicate
> (assumed, not checked). B, report an uncertain outcome and check status first:
> slower, and a blind manual retry could still duplicate. Checked: the endpoint
> takes no idempotency key (hypothetical `api/upload.ts:42`). Recommendation: B
> until deduplication exists, because duplicates are hard to undo. Which do you want?

## Solver patterns

Use a pattern when it changes the next action.

**Falsifiable predictions.** List the explanations that source and observations
support. For each, state what a specific probe would show and what result would
retire it. Run the cheapest separating probe, changing one variable at a time.

**Symptom-sensitive diagnostic.** Before theorizing, get one runnable,
deterministic check that reproduces the reported symptom, not a nearby failure.
For flaky failures, report the observed rate. If no check can be built, record
what was tried and what access would help. Redact secrets.

**Independent expected values.** Derive expected outputs from the spec, a worked
example or recorded behavior, never from the code under test, and note the
derivation beside the assertion.

**Original scenario before and after.** After a fix, rerun the original unreduced
scenario and the minimized regression check, and record both outcomes.

**Abstraction deletion,** only when a layer is in question: if removing it would
push no complexity into callers, it is a pass-through.

**Contrasting designs,** only for consequential interfaces: sketch two or three
deliberately different designs with a usage example and weak spot each, and
compare caller effort, where change concentrates, and testability.

## Limits

This reference paraphrases ideas from
[Matt Pocock's pinned skills](https://github.com/mattpocock/skills/tree/49dd158d1076134a641b33efb035946536778336)
(MIT): grilling, diagnosing bugs and codebase design. It deliberately omits their
yes-accepts-recommendation wording, fixed hypothesis counts and required
sub-agent counts. Worker briefs and owner verification live in
[model routing](model-routing.md). None of this has been shown to improve
accuracy, reduce user interventions or lower cost.
