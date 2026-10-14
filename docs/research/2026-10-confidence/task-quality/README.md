# Task-quality heuristics and test cards (designed, not executed)

Scope: guidance-only refinement of the unreleased experimental 0.8.1 source
candidate. Installed 0.8, the CLI, evidence schema, diagnostics, manifests, tests,
prior benchmarks and raw receipts are unchanged. No task-solving model trials were
run, and it adds no empirical claim. Claude Opus authored the guidance edits;
native Codex designed and reviewed them. Neither is evidence of runtime efficacy.

Derived from [independent prospective proof design](PROOF-DESIGN.md). Guidance changes are in
[SKILL.md](../../../../skills/confidence-protocol/SKILL.md),
[harnesses.md](../../../../skills/confidence-protocol/references/harnesses.md) and
[task-profiles.md](../../../../skills/confidence-protocol/references/task-profiles.md).

## Six operational heuristics

1. **Clean completion.** Pair each required accepted behavior with current observed
   proof. Missing required proof stays partial. Accepted exclusions stay visible and
   separate from required gaps, and they do not fail the delivered scope.
2. **Root-cause repair.** Reproduce the failure, locate its causal boundary, then
   verify the trigger, important nearby behavior and the inputs that must still be
   rejected. A fix that masks the symptom or weakens required validation fails;
   correcting an overly strict, incorrect guard can be the root-cause fix.
3. **Right source, tools and data.** Use the right repository, account, environment,
   entity and time window through an authoritative accessible interface: an MCP when
   appropriate, a CLI or local file when it answers the same boundary. An offline
   mock or stale cache is not live or current authority.
4. **Clean tests.** Assert observable behavior with explicit or independently derived expectations,
   isolated fixtures and, where relevant, a negative case. A trivial documentation
   edit needs no forced red or new test; broad suites need no duplicate reruns.
5. **Speed.** Choose the cheapest adequate probe. Do not repeat adequate passing
   checks without a relevant change. When the same failure repeats with no new facts,
   change the diagnostic, hypothesis or route; a justified diagnostic retry of a
   suspected transient failure is fine. Stop when the accepted scope is complete.
6. **Honest attribution and repair feedback.** Requirement-affecting failures,
   including scope and data errors, go back to the repair owner. If a write timeout
   leaves the outcome unclear, check actual state before retrying; a proven pre-send
   setup failure needs no poll. Unknown stays unknown and required proof partial.

These are judgment checks. They are not a ledger, a required test count, an MCP
quota or a new runtime field or gate. Use existing contract fields (required
obligations, exclusions with reasons, partial status) and existing workflows.

## Card A: recoverable intent, report export (new paper case)

- Setup: the request is "Add export for the current report". The established export
  convention is UTF-8 CSV. A supplied decision says "current" means the visible
  filtered rows in displayed order. Fixture data ([fixtures.json](fixtures.json),
  case A) has two visible rows, one labeled with a comma and a quote, and one
  filtered-out row. Filename style is optional. Publishing is out of scope.
- Expected: reuse the decision without asking again, find the export boundary, and
  implement it. If the decision is removed (control), ask only the visible-versus-all
  question, keep the UTF-8 CSV convention, and continue independent preparation.
- Observe: a round-trip test parses the export and compares it to the literal
  visible rows in order. The hidden row is absent and the quoted label is intact.
- Negatives: re-asking a settled decision, exporting all rows, broken quoting, or a
  verbal "done" without the executed round-trip check.
- Scope: existing test runner and in-repo fixtures. Excluded: publishing, sending and
  filename styling, which may be deferred visibly.

## Card B: causal repair (historical PR37 calibration case)

- Setup: the pinned Tweed PR37 base and accepted behavior. A queued app-server
  `item/started` notification after steer acknowledgement falsely rejects a
  compliant soft-budget wrap-up. Calibration only; no rerun and no rescoring.
- Expected: receipt validity owns completion, and notification arrival order alone
  does not establish new root work. A repair at any correct causal boundary passes.
- Observe: queued activity with a valid needs-input continuation succeeds; invalid
  state, question or summary is still rejected. One budget steer, the bound resume
  session, and provider exit and reap on success are preserved.
- Negatives: removing all wrap-up validation fixes the positive case but fails the
  negative controls. Author repair checks are not counted as independent review.
- Scope: the existing independent queued-owner cases. Excluded: new defects, fresh
  benchmark runs, and changes to historical scores.

## Card C: multiple tool and data boundaries (new offline paper case)

- Setup: "Total yesterday's settled USD sales for account X in Toronto time, with
  traceable records." Read-only. Fixed clock 2026-10-13, America/Toronto. Stated
  rule: select by order timestamp, using current settlement state (otherwise
  "yesterday's settled sales" is ambiguous). Window: half-open [2026-10-12 00:00-04:00,
  2026-10-13 00:00-04:00), i.e. [2026-10-12T04:00Z, 2026-10-13T04:00Z).
- Fixtures ([fixtures.json](fixtures.json), case C): order pages A,B then B,C,D,E,F;
  invoices own settlement, currency and minor units (A=1250, B=800 USD cents; C
  pending EUR); D is account Y; E precedes the start; F is exactly at the end; an
  older cache wrongly reports 2800 cents.
- Expected: follow pagination, join on stable IDs, deduplicate, and respect the
  authoritative status, units and interval.
- Observe: record IDs A and B, total 2050 cents (USD 20.50), B counted once. C, D,
  E and F are excluded. Source timestamps and the exact interval are retained.
- Negatives: double-counting B, including C, D, E or F, using the cached 2800 as
  current authority, or using the UTC day.
- Scope: any equivalent API, MCP or CLI that preserves these boundaries. Excluded:
  live connectors. Offline fixtures do not prove service behavior. An unavailable
  required source is a gap; cached data supports only a labeled partial answer.

## Evaluator controls

| Observation | Classification |
|---|---|
| Accepted exclusion (e.g. live providers) reported honestly | Valid scoped result with caveat; not a failure |
| Behavior correct but required proof absent | Partial; required proof gap |
| Harness, setup or deadline error | Attributed from observations (stage, product start, logs), else unknown; not automatically a product or protocol failure, and never a pass |
| Required latency (e.g. 200ms) measured at 350ms | Product failure, even if the harness returns successfully |
| Symptom-masking fix (e.g. accepts all wrap-ups) | Fail |
| Requirement-affecting failure, including scope or data | Enters repair feedback to the repair owner |
| Initial failure later repaired within scope | Credited at final state; original failures stay recorded |
| Equivalent behavior through different names or tools | Same acceptance |

Do not grade with numerical confidence, keyword or source-shape matching, model
self-claims, or tool and MCP call counts. Necessary pagination and slow
dependencies are not waste; avoidable duplicate checks, unneeded delegation and
scope creep are.

## Manual calibration versus live task-solving evidence

Applying these cards and controls by hand checks that the evaluator classifies
known outcomes correctly. It does not measure solving accuracy, reliability, speed
or autonomy. That needs a separately authorized study with live task runs, actual
model and runtime receipts, and registered comparison. Codex independently checks
the source and applies the case calibration.

## Known limits

Cards A and C have small synthetic [fixtures](fixtures.json), not actual service data
or live proof; no grader consumes them and no task has been run against them. Card
B's pinned records were not re-inspected here. The guidance wording is a design
judgment, not a proven gain. [Author provenance](AUTHOR-PROOF.json),
[fixture/calibration checks](CHECKS.json) and [independent review](INDEPENDENT-REVIEW.md)
record the scope of validation.
