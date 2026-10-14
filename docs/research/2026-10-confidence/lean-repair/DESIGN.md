# Lean repair revision 0.8.1: design

Status: **experimental source candidate**. Source version 0.8.1 is not installed
automatically; the installed 0.8.0 stays unchanged until a measured comparison
supports this revision. This note records the design before any comparison
attempt. It contains no results and claims no accuracy, cost or autonomy gain.

Implementation: Claude Opus (`claude-opus-5-5`) as development lead, editing only
the owned files listed below. Coordination, package checks and fresh independent
review: Codex. The prospective proof plan was written beforehand by a separate
native Codex task (`/root/lean_repair_proof_design`). Haiku supplied a bounded
source-fact extraction; the coordinator retraced its quotes, and its implications
were treated as candidates.

## Observed gaps versus hypotheses

Observed in the [0.8 pilot](../v08-spotcheck/REPORT.md):

1. All four routing candidates, and the accepted reference, failed the stale-turn
   positive case of an additional routing diagnostic, while the active-turn
   negative controls of that same additional diagnostic passed. A passing primary
   suite and a passing reference did not establish the requirement.
2. An original-guidance PR40 pass accepted a value that the requirement excluded
   because the primary tests omitted that spelling. Independent review found it;
   that review did not find the stale-turn defect.
3. All four intake episodes used every round and ended `ready=false`. Both resume
   episodes asked the numeric-precedence decision that the keyword simulator did
   not answer. This is evidence that asked and answered decisions differ and that
   the stopping point was unclear. It is not evidence of good or bad intake.

Hypotheses, not shown by that pilot:

- A concrete readiness rule (stop when no required choice or necessary fact blocks
  the next authorized action; defer optional choices visibly) reduces both
  premature stopping and question accumulation.
- Asking for a relevant negative or boundary case in the completion pairing, and
  stating that agreement does not close a known counterexample, makes coverage
  misses of types 1 and 2 more likely to be found before completion.
- Returning reviewer findings to the implementer as a concrete packet, with the
  repairer's provenance recorded, makes repairs more targeted and keeps author
  checks from being reported as independent review.

The pilot ran neither the staged developer/check/repair loop nor Haiku or Codex
roles, so it gives no evidence about the third hypothesis.

## Exact changes

Each change replaces or extends existing sentences; no new section, step, field,
mode or schema.

- `SKILL.md` routing paragraph: Opus owns repair as well as implementation and
  diagnosis; Codex returns concrete requirement-affecting findings to Opus.
- `SKILL.md` review paragraph: an actor's check of its own implementation or
  repair is author evidence, not independent review of that change.
- `SKILL.md` completion pairing: include a relevant negative or boundary case where
  one could refute the claim; an unresolved known counterexample is a gap that a
  completion claim, passing suite, review agreement or passing accepted reference
  does not close. "Where one could refute the claim" limits this to relevant
  cases; it is not an exhaustive boundary checklist.
- `references/intent-flows.md` readiness: the two readiness paragraphs became a
  stopping rule. Discover facts first; ask only open consequential choices; defer
  optional choices (extra UI, logging, reporting surfaces) visibly when existing
  behavior and scope are preserved; keep unknown necessary facts as required gaps;
  require no proof that later discovery cannot matter; keep reading sources
  separate from settling choices. The existing rules against re-asking settled
  decisions and inferring unanswered ones are kept.
- `references/model-routing.md`: Opus role includes repair; Codex sends a finding
  packet (requirement, counterexample or location, executed or reproducible check);
  Opus repairs, reruns and returns the current diff and gaps; Codex rechecks. The
  handoff covers delegated substantial work, not Quick tasks. Codex fallback repair
  is allowed, and Codex is recorded as author of that repair. Required independent
  review uses an actor that did not implement or repair the scope, as
  `complex-tasks.md` already requires. One `Repairs:` line in the existing
  verification record.
- `references/harnesses.md` Claude-from-Codex paragraph: findings return to Opus or
  the implementation owner for repair; Codex rechecks and integrates; fallback
  repair records Codex as author (see the integration correction below).
- `README.md` and `CHANGELOG.md` summaries; `.codex-plugin/plugin.json` and
  `diagnostics.py` `TOOL_VERSION` set to 0.8.1.

Unchanged: `references/question-patterns.md` (its fact-first and neutral-choice
guidance already fits the new rule), Haiku's optional bounded role and
source-retrace check, direct fallback, model and provider preferences, Critical
proof-design and adversarial roles, component availability/read/relevance/fallback
rules, the Matt Pocock adaptation notes, CLI, evidence schema, tests and prior
studies.

The guidance avoids task-specific identifiers from the pilot, such as stale turns
or numeric flags. The changes target the general failure, a required boundary
missing from proof, and not those instances.

## Protocol versus evaluation controller

The protocol is guidance for a working agent. It adds no dispatcher, and `next`
launches nothing. In the comparison, the evaluation controller is separate. It
freezes tasks, prompts, requirements, baseline source, grader, budgets and packet
boundaries; runs each stage; and records outcomes. As `model-routing.md` already
states, a registered experiment's fixed routes govern only that experiment.
Controller behavior is not protocol behavior, and protocol text is not evidence
that the controller ran a stage.

## Comparison and its limits

The frozen prospective plan uses public historical Tweed PR20 (model precedence),
PR23 (reasoning propagation) and PR37 (post-steer queue ordering). It excludes
PR31/32/34/35/39/40 and avoids PR43/44. "Fresh" means these task identities were
not previously replayed; the mechanisms may be familiar. Each task is a behavioral
slice, not full-PR acceptance. Owner checks use public behavior with offline
provider transport and a consequential boundary, pinned base failure and reference
success, plus a representation-equivalence control. Solvers get the base and the
accepted prompt only.

Pre-repair and post-repair outcomes are reported separately, with repair actor and
changed paths. Arms get equal budgets and packet boundaries. Three tasks are
feasibility evidence and cannot support a general quality, accuracy, cost or
autonomy claim. A passing reference or oracle is a comparison subject, not a
definition of correctness, so a later counterexample stays reportable. Haiku and
cross-provider effects are measured only if the controller actually runs them.

## Integration correction

`references/harnesses.md` previously said that when Claude is called from Codex,
"Codex should reconcile concrete findings, repair real defects, and capture fresh
proof", which conflicted with Opus owning repair. After independent Codex review,
Opus edited that sentence: Codex now returns real defects to Opus or the
implementation owner for repair, then rechecks, integrates and captures fresh
proof; authorized Codex fallback repair records Codex as its author. It links to
`model-routing.md` instead of repeating the handoff, and permission, cost and
runtime rules are unchanged. This is a text correction, not an outcome: source
0.8.1 remains experimental and uninstalled, and no task outcomes are known yet.
