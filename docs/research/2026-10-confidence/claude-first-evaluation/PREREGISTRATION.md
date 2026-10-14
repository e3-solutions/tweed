# Claude-first routing and prompt comparison — 13 October 2026

This is a new exploratory study, separate from the original84 and hybrid V1/V2.
The policy follows the user's Claude-first preference; it does not presuppose
Opus superiority or that Haiku beats Luna/Terra. No new historical solver outcomes
were used to select these six reused public PR tasks or tune the instruction text.
The tasks and some older outcomes are familiar; this is not an unseen holdout.

## Main worker comparison

Six qualified behavioral PR slices (31,32,34,35,39,40), two fresh attempts per task,
four arms, exactly 48 assigned cells. A fixed seeded shuffle schedules the cells.
Each is a single bounded implementation episode, not an end-to-end Critical CP
workflow. Recursive peer calls are explicitly unavailable. Requirements are fully
specified, so these episodes do not measure user-intent clarification.

| Arm | Main route | Instruction tree |
| --- | --- | --- |
| baseline-opus | requested/observed Opus5.5, medium | exact installed-equivalent v0.6 at 7180b6d |
| enhanced-opus | requested/observed Opus5.5, medium | proposed v0.7 instruction bundle |
| enhanced-haiku | requested/observed Haiku5.5, medium | same proposed v0.7 bundle |
| enhanced-codex | requested Astra, medium | same proposed v0.7 bundle |

Sol6.1's fresh account-bound CLI request was rejected before registration; Astra
passed the toy write/test and owner assertion. This is an explicit pre-registration
route selection, not a failed-cell fallback. Actual Codex response-model identity
may remain unobserved. Claude assistant-event identifiers must match exactly.
A successful request does not authenticate underlying weights.

The primary contrasts are enhanced-opus minus baseline-opus (full instruction
bundle effect), enhanced-haiku minus enhanced-opus, and enhanced-codex minus
enhanced-opus (main provider/model/harness contrasts under the enhanced bundle).
Do not attribute the bundle effect solely to question wording: routing, harness
and question/solver reference text also differ. Do not infer a pure weight effect
from different providers' system prompts and internal tools.

Every arm gets identical CP0.6 executable/assets bytes, the same seven operational
MCP tools and independently restored baseline/held-out tests. Selected SKILL and
references are mounted once at .protocol; no duplicate core policy. Visible tests,
production scope, sources, check commands and human task requirements match.
Each main call has 240 seconds. Claude receives a USD2 runtime guard; Codex has no
corresponding USD guard, and equal effort labels do not imply equal compute.
Maximum concurrency is three. CLI estimates are not subscription bills; unknown
USD stays unknown. Timing is descriptive, not an efficiency conclusion.

Before inference, independently qualify confinement, actual MCP transport,
requested/observed model checks, lifecycle/status checks and all six baseline-RED/
head-GREEN oracles plus two behaviorally equivalent rename controls. Freeze source,
policy, runtime, oracle, controller, request roster and actual catalog snapshots.
An initial no-inference preparation was retained when its mutable user catalog
input was replaced by an immutable model-metadata snapshot. Final registration
identifies the adopted preparation. Started cells are never retried automatically;
interrupted, missing, invalid and unsuccessful assignments remain visible.

Report all task/arm/repeat outcomes: raw selected-oracle acceptance, transport and
source eligibility, assigned verified acceptance, valid worker declaration,
false-complete declarations and missing terminal state. A worker complete flag is
not full CP delivery closure. Group paired effects at the six task clusters,
averaging repeats. Report every registered contrast with per-task differences and
exact whole-task bootstrap intervals (6^6 empirical resamples), treated as small
purposive-sample descriptions. Never rank models from one favorable contrast.

## Scripted intake comparison

Twelve real model interview episodes: current versus enhanced relevant policy,
three ambiguous requests derived from PR31/34/32, two repeats each. Both use
Opus5.5 medium and the same supplied source facts, output schema and scripted-user
answer boundary. Seed-shuffle order before calls; maximum concurrency two. Each
session has at most three rounds, each at most120 seconds/USD0.6. Empty operational
tool inventory, no outside source, no code writes. Fresh calls receive the whole
retained conversation; this is text-transcript continuity, not native session reuse.

A frozen keyword user oracle answers only recognized behavior questions. Its
hidden ledger does not enter the model context. Keep exact questions, answers and
settled choices. Measure recognized decision coverage, readiness before actual
answers, repeated decision questions, final readiness and missing outcomes.
A separate transcript reviewer checks whether the questions truly seek the
recognized decision, final choices follow human answers, and known facts or
answered preferences are unnecessarily asked. Keyword matches alone do not prove
semantic clarification, and these episodes do not establish user satisfaction or
answer-dependent production implementation. Do not optimize question count.

## Blinded quality and follow-up probe

Use a fresh Codex reviewer with no arm/model labels or model summaries. Supply
requirements and anonymized production source/diffs, not accepted head solutions.
Separate correctness, missed requirements, concrete removable complexity and
unsupported stylistic preference. Findings need locations and an observable
consequence or a specific removable layer. Run claimed counterexamples where
possible. Report reviewer judgments as limited evidence, not ground truth.
No model-generated aggregate quality score or LOC threshold decides readiness.

Predeclare eight PR40 follow-up assignments, one for every original arm/repeat,
after its first-stage tree freezes. Every available regular artifact gets the same
fresh Opus5.5 medium120-second/USD1 worker and the same new requirement: accept
case-insensitive whitespace-trimmed environment token `unbounded` with exactly the
existing `off` semantics while preserving all originally required behavior.
Restore trusted original tests before workers run. Keep the novel public CLI/
checkpoint check outside worker access, qualify it with old-head RED and a bounded
correct alternative GREEN, and re-run the original independent acceptance oracle.
Freeze this probe's implementation, rubric, inputs and output roster before any
follow-up inference. Keep missing first-stage artifacts explicitly not run.

Compare extension success plus original preservation; record changed files/lines,
actual test calls, elapsed/usage and remaining gaps. Report initially accepted
artifacts separately: improving a broken initial implementation is repair as well
as extension. This is one maintenance-change probe, not a broad maintainability
benchmark. Any later unplanned diagnostic is labeled post hoc and does not alter
registered primary grades or become a favorable replacement attempt.

## Delivery and interpretation

Codex is the coordinator and verification owner. Actual Opus authoring and Haiku
source extraction have distinct preserved packets/receipts and owner reconciliation;
actual implementation capability requires tool-enabled worker results, not those
packet reviews. Independent proof design precedes implementation; adversarial
preflight has already rejected three new-controller mistakes before task calls.

The normal plugin adds conditional guidance and preferences, not an orchestration
runtime or external dependency. Research controllers/tests/results are excluded
from the install archive. Final public artifacts must preserve all assignments,
selected checks, evidence hashes and limits without raw private transcripts,
credentials, user paths or unapproved messages. Install only the verified release
bytes, retain the old plugin backup, and report what the experiments support even
when a preferred route is weaker on these tasks.
