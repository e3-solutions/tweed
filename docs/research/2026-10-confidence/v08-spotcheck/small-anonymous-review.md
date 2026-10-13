# Small anonymous packet review

Only review-packets C01-C08 production snapshots/requirements/patches and I01-I04 interviews. Qualitative independent review; no policy ranking.

One confirmed requirement miss: C08 accepts `off` on the numeric-only budget CLI flag. Other candidate observations below are bounded source findings, not a correctness certification or inferred policy ranking.

Native Codex reviewer; actual model unobserved. Nominal anonymity was maintained by limiting reads to packet files; this was not OS confinement. No mapping, study result, policy, grade or previous jury was read.

## Production observations

### C01 (T2)

No confirmed missed requirement identified in this bounded review.

Numeric CLI input has a strict positive finite validator; optional runtime budget maps None/off to disabled; new checkpoint serializes disabled as null.
Evidence: review-packets/C01/production/bonaparte:777–817; review-packets/C01/production/bonaparte:1347–1349; review-packets/C01/production/bonaparte_checkpoint.py:219–233.

Disabled run_phase builds no deadline, waits with timeout None, and bypasses steering on TimeoutError. Resume uses a distinct off marker for explicit disable and preserves persisted value when override is omitted.
Evidence: review-packets/C01/production/bonaparte:1065–1109; review-packets/C01/production/bonaparte:1505–1511; review-packets/C01/production/bonaparte:1539–1563; review-packets/C01/production/bonaparte:1749–1758.

Complexity: The strict/optional/default resolvers and resume marker add several small adapters, but the distinctions serve numeric-only CLI validation and omitted-versus-disabled resume behavior. No clearly unnecessary machinery identified.
Evidence: review-packets/C01/production/bonaparte:777–817.

### C02 (T1)

No confirmed missed requirement identified in this bounded review.

Driver ownership filter suppresses a child thread terminal and a legacy nonactive terminal before the run loop; active legacy terminal remains accepted. Agent receipt capture also checks turn identity and ownership while progress is still fed.
Evidence: review-packets/C02/production/bonaparte_native.py:100–114; review-packets/C02/production/bonaparte_native.py:301–330.

Final receipt fallback and finally-based driver cleanup remain present.
Evidence: review-packets/C02/production/bonaparte:666–692.

Interpretation risk: A completion on the coordinator thread with a stale turn ID is still returned and causes the run loop to raise. This preserves the prepatch wrong-turn guard, but the broad phrase only active thread/turn may establish outcome could instead require ignoring stale coordinator turns. Not classified as a confirmed miss without resolving that interpretation.
Evidence: review-packets/C02/production/bonaparte_native.py:108–114; review-packets/C02/production/bonaparte:650–654.

Complexity: One ownership helper reused for terminal and receipt selection; no substantial unrelated complexity.
Evidence: review-packets/C02/production/bonaparte_native.py:100–114; review-packets/C02/production/bonaparte_native.py:301–330.

### C03 (T1)

No confirmed missed requirement identified in this bounded review.

Both event-loop paths accept only the active turn and reject a conflicting thread identity from params or completed_turn. Legacy active-turn completion is accepted; stale coordinator completion is ignored.
Evidence: review-packets/C03/production/bonaparte:412–428; review-packets/C03/production/bonaparte:630–635; review-packets/C03/production/bonaparte:667–670.

Existing receipt capture remains scoped to exact thread and turn; final receipt fallback and driver cleanup remain intact.
Evidence: review-packets/C03/production/bonaparte_native.py:284–309; review-packets/C03/production/bonaparte:688–710.

Complexity: Single boolean helper; examining both possible thread containers is conservative and inexpensive. No clearly unnecessary expansion identified.
Evidence: review-packets/C03/production/bonaparte:412–428.

### C04 (T1)

No confirmed missed requirement identified in this bounded review.

Filters child terminals in both polling paths; accepts active legacy completion with no thread identity; an additional terminal-is-None guard prevents later matching terminals replacing an already selected terminal while waiting for steer acknowledgement.
Evidence: review-packets/C04/production/bonaparte:412–433; review-packets/C04/production/bonaparte:635–640; review-packets/C04/production/bonaparte:672–677.

Scoped receipt capture, final receipt fallback and finally cleanup remain present.
Evidence: review-packets/C04/production/bonaparte_native.py:284–309; review-packets/C04/production/bonaparte:695–716.

Interpretation risk: Stale coordinator turn IDs raise rather than being ignored. This is the prepatch guard, with the same unresolved broad-requirement interpretation as C02. If params.threadId and completed_turn.threadId conflict, params takes precedence; the packet does not establish that such contradictory events are supported.
Evidence: review-packets/C04/production/bonaparte:423–433.

Complexity: A small helper plus a terminal replacement guard is proportionate; no clearly unnecessary machinery identified.
Evidence: review-packets/C04/production/bonaparte:412–433; review-packets/C04/production/bonaparte:672–677.

### C05 (T2)

No confirmed missed requirement identified in this bounded review.

Uses an identity sentinel for explicit resume disable, converts it to None for checkpoint persistence, and keeps omission separate. Disabled runtime has no deadline and guards steering; CLI numeric off is rejected.
Evidence: review-packets/C05/production/bonaparte:784–819; review-packets/C05/production/bonaparte:1065–1100; review-packets/C05/production/bonaparte:1504–1510; review-packets/C05/production/bonaparte:1538–1562.

Checkpoint validator permits null; new-question checkpoint passes the optional resolver. CLI mutually exclusive group separates numeric and disable flags.
Evidence: review-packets/C05/production/bonaparte_checkpoint.py:219–233; review-packets/C05/production/bonaparte:1346–1348; review-packets/C05/production/bonaparte:1726–1759.

Complexity: Custom sentinel class is more ceremony than a bare object but its repr aids debugging; repeated normalization around resume is local and justified by retaining omitted/disabled distinction. No material unnecessary complexity found.
Evidence: review-packets/C05/production/bonaparte:59–67; review-packets/C05/production/bonaparte:1504–1510; review-packets/C05/production/bonaparte:1538–1541.

### C06 (T2)

No confirmed missed requirement identified in this bounded review.

Disabled runtime waits without deadline/steering. Resume normalizes the sentinel to null but separately records whether an override was supplied, so numeric override and disabled override both persist.
Evidence: review-packets/C06/production/bonaparte:1065–1085; review-packets/C06/production/bonaparte:1510–1516; review-packets/C06/production/bonaparte:1544–1547.

CLI uses manual mutual-exclusion validation and a budget parsing helper; numeric off is rejected, numeric CLI overrides environment off, omission on resume preserves saved choice.
Evidence: review-packets/C06/production/bonaparte:1741–1767; review-packets/C06/production/bonaparte:1813–1820; review-packets/C06/production/bonaparte_checkpoint.py:219–233.

Complexity: Custom sentinel and explicit override boolean encode the necessary third state. Manual conflict validation duplicates an argparse capability but is a minor local choice, not material overengineering.
Evidence: review-packets/C06/production/bonaparte:772–802; review-packets/C06/production/bonaparte:1510–1516; review-packets/C06/production/bonaparte:1754–1765.

### C07 (T1)

No confirmed missed requirement identified in this bounded review.

Both event-loop paths filter child thread completion and accept only matching active-turn legacy completion. Existing receipt selection and cleanup are preserved.
Evidence: review-packets/C07/production/bonaparte:412–431; review-packets/C07/production/bonaparte:633–639; review-packets/C07/production/bonaparte:671–677; review-packets/C07/production/bonaparte_native.py:284–309; review-packets/C07/production/bonaparte:695–716.

Interpretation risk: Stale coordinator turn IDs retain the prepatch RuntimeError behavior. Helper reads thread identity only from params; nested-only threadId attribution is not established by the packet requirements, so this is not counted as a confirmed defect.
Evidence: review-packets/C07/production/bonaparte:423–431.

Complexity: One dict-or-None helper reused across both paths; no clearly unnecessary machinery identified.
Evidence: review-packets/C07/production/bonaparte:412–431.

### C08 (T2)

**medium: The general resolver accepts string off as disabled, and parse sends the numeric CLI flag through that resolver. --soft-phase-budget-seconds off scope fixture returns a disabled None budget instead of rejecting invalid numeric input. On resume the same None is interpreted as no override, so it may silently preserve a positive saved budget.**

Evidence: review-packets/C08/production/bonaparte:777–780; review-packets/C08/production/bonaparte:1789–1793; review-packets/C08/production/bonaparte:1500–1505; review-packets/C08/production/bonaparte:1533–1536; review-packets/C08/requirements.json#/requirements. AST-extracted production parse and resolver returned None for --soft-phase-budget-seconds off; no provider/import execution.

Correct disable flag uses a resume marker; runtime None disables deadline/steering and checkpoint validator accepts null. Explicit positive numeric CLI overrides environment off.
Evidence: review-packets/C08/production/bonaparte:1058–1080; review-packets/C08/production/bonaparte:1783–1793; review-packets/C08/production/bonaparte_checkpoint.py:219–233.

Interpretation risk: Omitted resume option still evaluates environment default before discarding it. An invalid environment value therefore prevents resuming even if the saved budget is valid; whether unused environment inputs must be rejected is not explicit enough to count as a second confirmed miss.
Evidence: review-packets/C08/production/bonaparte:1791–1793.

Complexity: Reusing one permissive resolver for runtime and numeric-only CLI conflates different contracts. Duplicate prevalidation/normalization on resume is minor; the main problem is insufficient separation of input semantics.
Evidence: review-packets/C08/production/bonaparte:777–795; review-packets/C08/production/bonaparte:1503–1505; review-packets/C08/production/bonaparte:1533–1536.

## Interviews

Question counts describe interaction volume, not quality ranking. Repetition after an unanswered question is distinct from re-asking an answered decision.

### I01

Verifiable excerpts:

- “Older notifications sometimes have no threadId.” — review-packets/I01/interview.json#/actual_history/0/assistant/questions/1
- “Keep child progress visible, but it must never replace the coordinator final receipt.” — review-packets/I01/interview.json#/actual_history/1/user/1
- “Which places must apply the coordinator-only completion rule:” — review-packets/I01/interview.json#/actual_history/4/assistant/questions/0

Question counts by round: 5, 2, 2; every round reports ready=false. Existing known facts and prior answers are respected.

**Asked:** Asked ownership, no-threadId legacy handling and child visibility in round 1, plus affected UI/API/alerts and unknown-event disposition.
Evidence: review-packets/I01/interview.json#/actual_history/0/assistant/questions.

**Settled:** All three scripted routing decisions were actually received and accurately recorded; later ownership repetition added no new decision.
Evidence: review-packets/I01/interview.json#/actual_history/1/user; review-packets/I01/interview.json#/actual_history/2/assistant/settled; review-packets/I01/interview.json#/actual_history/3/user.

**Safely unresolved:** Affected surfaces and logging/display of unrelated events received no direct answer; keeping those unresolved is honest. Their treatment could be deferred by preserving existing behavior if source inspection confirms the routing fix needs no broader changes.
Evidence: review-packets/I01/interview.json#/actual_history/4/assistant/missing.

**Redundancy:** The two unanswered scope/disposition questions recur. They do not re-ask settled legacy, ownership or progress rules, but expand the intake beyond the minimum routing rule and continue blocking readiness on potentially optional choices.
Evidence: review-packets/I01/interview.json#/actual_history/2/assistant/questions; review-packets/I01/interview.json#/actual_history/4/assistant/questions.

**Readiness:** Reports ready=false in every round. Core routing choices are settled; full-scope readiness cannot be decided from these source facts alone. No false ready claim.
Evidence: review-packets/I01/interview.json#/actual_history/4/assistant/ready.

### I02

Verifiable excerpts:

- “should that CLI value replace the budget saved in the checkpoint, including turning a disabled budget back on” — review-packets/I02/interview.json#/actual_history/2/assistant/questions/0
- “When the resume option is omitted, preserve the saved budget choice, including disabled.” — review-packets/I02/interview.json#/actual_history/1/user/0
- “Whether a budget option passed on resume replaces the budget saved in the checkpoint.” — review-packets/I02/interview.json#/actual_history/4/assistant/missing/0

Question counts by round: 6, 6, 6; every round reports ready=false. Existing known facts and prior answers are respected.

**Asked:** Asked source precedence, disable representation, persistence, invalid inputs, meaning of reliable resume and startup display. Later questions directly ask whether explicit CLI on resume replaces a saved disabled choice; valid semantic wording even though numeric-over-saved scripted answer was never received.
Evidence: review-packets/I02/interview.json#/actual_history/0/assistant/questions; review-packets/I02/interview.json#/actual_history/2/assistant/questions/0; review-packets/I02/interview.json#/actual_history/4/assistant/questions/0.

**Settled:** Only omitted-preserves and no-silent-environment-replacement were received. No explicit numeric override answer appears in actual user messages.
Evidence: review-packets/I02/interview.json#/actual_history/1/user; review-packets/I02/interview.json#/actual_history/3/user; review-packets/I02/interview.json#/actual_history/5/user.

**Safely unresolved:** Explicit CLI precedence, off spelling/form, invalid-value policy, missing/default checkpoint behavior and fresh environment default remain unanswered. Distinguishes no silent replacement from ignore/warn/refuse policy without inventing an answer.
Evidence: review-packets/I02/interview.json#/actual_history/4/assistant/missing.

**Redundancy:** Rounds 2 and 3 repeat six largely unchanged unanswered questions; this is repetitive intake, not redundancy with actually settled answers. Startup display and wider reliable-resume scope are optional expansion candidates and should not automatically block a minimal fix.
Evidence: review-packets/I02/interview.json#/actual_history/2/assistant/questions; review-packets/I02/interview.json#/actual_history/4/assistant/questions.

**Readiness:** ready=false is defensible: important behavior choices have no received answers. Do not equate the simulator failing to supply numeric-over-saved with the assistant failing to ask that choice.
Evidence: review-packets/I02/interview.json#/actual_history/4/assistant/ready.

### I03

Verifiable excerpts:

- “should it count as complete right away, even if child turns are still running?” — review-packets/I03/interview.json#/actual_history/2/assistant/questions/0
- “Only the active coordinator thread and turn can establish its completion.” — review-packets/I03/interview.json#/actual_history/3/user/1
- “says which event can trigger it, not whether it waits for children.” — review-packets/I03/interview.json#/actual_history/4/assistant/missing/0

Question counts by round: 4, 1, 1; every round reports ready=false. Existing known facts and prior answers are respected.

**Asked:** Round 1 asks coordinator completion versus waiting for children, legacy attribution, child visibility, and active-turn matching. Later rounds focus on the child-wait decision.
Evidence: review-packets/I03/interview.json#/actual_history/0/assistant/questions; review-packets/I03/interview.json#/actual_history/2/assistant/questions; review-packets/I03/interview.json#/actual_history/4/assistant/questions.

**Settled:** Legacy matching, progress visibility and active ownership were received, recognized, and not re-asked as unanswered.
Evidence: review-packets/I03/interview.json#/actual_history/1/user; review-packets/I03/interview.json#/actual_history/2/assistant/settled.

**Safely unresolved:** User replies identify which event owns completion but never explicitly decide whether completion waits for outstanding children. The transcript correctly separates owner identity from a lifecycle barrier. The scripted ledger contains no direct answer to that barrier.
Evidence: review-packets/I03/interview.json#/actual_history/3/user; review-packets/I03/interview.json#/actual_history/4/assistant/missing; review-packets/I03/interview.json#/scripted_decisions.

**Redundancy:** The single waiting-for-children question is repeated after nonresponsive scripted answers. It remains unanswered, so repetition is not re-asking an already settled choice. A barrier may be unnecessary scope expansion if existing lifecycle is to be preserved; the packet supplies no baseline lifecycle fact.
Evidence: review-packets/I03/interview.json#/actual_history/2/assistant/questions/0; review-packets/I03/interview.json#/actual_history/4/assistant/questions/0.

**Readiness:** ready=false honestly reflects its remaining consequential lifecycle question; core routing identity decisions are ready. Ledger completion alone cannot establish overall readiness.
Evidence: review-packets/I03/interview.json#/actual_history/4/assistant/ready.

### I04

Verifiable excerpts:

- “should the CLI value (A) win quietly, (B) win with a warning, (C) lose to the checkpoint” — review-packets/I04/interview.json#/actual_history/2/assistant/questions/2
- “When the resume option is omitted, preserve the saved budget choice, including disabled.” — review-packets/I04/interview.json#/actual_history/3/user/0
- “This rules out quiet env-over-checkpoint replacement.” — review-packets/I04/interview.json#/actual_history/2/assistant/settled/1

Question counts by round: 8, 8, 7; every round reports ready=false. Existing known facts and prior answers are respected.

**Asked:** Asked off representation, full precedence, resume persistence/reactivation, mismatch policy, invalid values, checkpoint effective value and broader reliable-resume scope. Later explicit-CLI versus saved questions cover positive reactivation semantically, even without the exact numeric keyword trigger.
Evidence: review-packets/I04/interview.json#/actual_history/0/assistant/questions; review-packets/I04/interview.json#/actual_history/2/assistant/questions/2; review-packets/I04/interview.json#/actual_history/4/assistant/questions/1.

**Settled:** Initially receives only no-silent-env-replacement, then omitted-preserves. No numeric-over-saved answer is actually received. Latest settled list recognizes that omission preserves disabled and does not claim explicit CLI precedence is known.
Evidence: review-packets/I04/interview.json#/actual_history/1/user; review-packets/I04/interview.json#/actual_history/3/user; review-packets/I04/interview.json#/actual_history/4/assistant/settled.

**Safely unresolved:** Off form, explicit CLI mismatch policy, invalid handling, fresh CLI/env priority and saved-default provenance remain unanswered. Warning/refusal on conflicting unused env remains a product choice; the answer about preserving saved budget does settle value selection when CLI is omitted.
Evidence: review-packets/I04/interview.json#/actual_history/4/assistant/missing.

**Redundancy:** Several precedence questions overlap initially and recur because answers are absent. After omission is answered, the main omitted-resume selection is no longer asked, but logging/refusal and saved-explicit provenance remain expanded decisions. No re-asking of existing flag names.
Evidence: review-packets/I04/interview.json#/actual_history/0/assistant/questions; review-packets/I04/interview.json#/actual_history/4/assistant/questions.

**Readiness:** ready=false is appropriate for unanswered disable/explicit-CLI/invalid policies. The interview asks more ancillary choices than needed to settle basic resume selection, but nonrecognition by the keyword simulator is not proof of failure to ask.
Evidence: review-packets/I04/interview.json#/actual_history/4/assistant/ready.

## Checks, limitations and source manifest

All 16 production files parse as Python. Narrow extracted-function checks confirmed the budget input distinction and routing outputs recorded in the JSON. These checks executed no provider or imported production dependencies.

- Qualitative evidence, not sole-authority correctness or benchmark claim.
- No production files changed; no provider workflows, hosted model calls, external services, new benchmark, publication or large test suite.
- Packet snapshots omit dependency/test fixtures; visible unittest commands not run because reading outside the packet is disallowed.
- All production files parsed as Python; narrow AST-extracted function checks use stdlib-only namespaces and stubs, not integration execution.
- Source locations and behavior findings are bounded to packet content. No definite defect found does not certify absence of defects.
- Scripted interview ledger is incomplete intent and keyword matching can miss valid phrasing; asked questions, received answers and readiness assessed separately.

The complete SHA-256 manifest covers all 36 packet files in [small-anonymous-review.json](small-anonymous-review.json), under `source_manifest`. It includes paths, byte counts and review use; full-source AST parsing does not mean a line-by-line audit of unrelated code.
