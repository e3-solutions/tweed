# Small 0.8 versus original-guidance pilot

The new guidance has a small advantage on the selected checks, but this pilot does **not** establish that it is a better Confidence Protocol. It produced two qualified passing deliveries out of four assigned attempts; original guidance produced one. Each had one timeout. Every routing candidate still failed the additional stale-turn boundary check, including the candidate that passed the primary routing tests. Clarification did not demonstrate a reliable improvement.

This is the new, small prospective pilot requested after the Opus-led revision. It does not replace or pool the earlier unfavorable 0.7 results. No guidance, installation, candidate patch or primary grader was repaired after seeing these results.

## Comparison and primary results

[Preregistration](PREREGISTRATION.md) was committed at `82b9f876d870b3b39b8a9d52cc7337a42f2d671e` before the first hosted attempt. Eight fresh implementation attempts replayed public [PR32](https://github.com/e3-solutions/tweed/pull/32) and [PR40](https://github.com/e3-solutions/tweed/pull/40): two repeats per task and policy. Both used requested and assistant-event-observed `claude-opus-5-5`, medium effort, Claude Code 2.1.285, a 240-second inference-stage limit and a USD 2 CLI guard. Each attempt performed offline transport qualification and used the same confined tool envelope.

Only the full guidance package changed: original 0.6 versus 0.8. Both arms shared current 0.8 executable/assets. This is neither an exact old-runtime replay nor a test of the complete Opus/Haiku/Codex delegation workflow. Peer and external-component execution were unavailable in both arms.

| Outcome, all assigned attempts | Original guidance | 0.8 guidance |
|---|---:|---:|
| Assigned | 4 | 4 |
| Qualified selected-check passes | 1 | 2 |
| Qualified selected-check failures | 2 | 1 |
| Timeout, delivery unqualified | 1 | 1 |
| `complete=true` with selected checks failing | 2 / 3 declarations | 1 / 3 declarations |

“Qualified” requires the observed model, actual tool inventory, valid provider terminal, lifecycle/cleanup and production scope. A pass is evidence for the selected tests, not a full-task certificate. All six qualified workers declared `complete=true` while also listing remaining caveats; the table retains the registered completion-flag definition rather than interpreting caveats as silence or a universal dishonest claim.

| Task | Original repeat 1 | Original repeat 2 | 0.8 repeat 1 | 0.8 repeat 2 |
|---|---|---|---|---|
| PR32: coordinator event routing | Fail | Fail | Fail | Pass |
| PR40: disabled budget/resume | Timeout / unknown delivery | Pass | Pass | Timeout / unknown delivery |

The primary PR32 oracle exercises seven public-boundary routing checks; PR40 exercises nine budget/resume checks. Their base-fail/head-pass controls and the PR40 representation-equivalence control passed before inference. Separate closure replays of all six qualified, digest-bound current source snapshots agree with their recorded grades. Neither timeout was retried. The retained code from both timeouts later passed the PR40 checks, but that diagnostic does not supply the missing valid terminal or convert either primary outcome into a delivered success.

## Stronger routing diagnostic: all candidates miss a case

The predeclared additional probe sends a same-thread stale work event after the soft-budget steer, then an otherwise valid active coordinator completion. The stale event should not establish active-turn work. All four routing candidates incorrectly raise `RuntimeError: coordinator started new work after soft-budget steer` and reject the valid receipt. The original base and accepted PR32 head also fail this positive case.

All six active-turn negative controls correctly reject new work with that exact guard error. Each observation exercised the steer, closed the mocked provider, exited without a diagnostic timeout and left the source bytes unchanged. These are offline fixtures, not live provider runs.

This exposes missing coverage in the primary oracle and a defect in the accepted reference on the stronger boundary. It does not retrospectively rewrite the registered grades. Four passing negative controls must not be reported as four successful routing implementations: **zero of four candidates satisfy both diagnostic cases**.

The diagnostic helper and intended comparison were frozen before inference. Its small execution driver was written after some outcomes were visible; that timing is disclosed in [input custody](INPUTS.json). The expected stale/active distinction comes from the task's active-owner requirement; the accepted head is a comparison subject, not an infallible definition of correctness.

## Clarification episodes

Four eligible Opus episodes used supplied facts and a frozen keyword-scripted user, maximum three rounds. All four used all three rounds and ended with `ready=false`; none triggered the simulator's premature-readiness flag. That alone does not establish either good intake or bad intake.

| Episode | Original | 0.8 |
|---|---:|---:|
| Notification ownership: questions across three rounds | 9 | 6 |
| Notification ownership: keyword answers delivered | 3 / 3 decisions | 3 / 3 decisions |
| Resume precedence: questions across three rounds | 18 | 23 |
| Resume precedence: keyword answers delivered | 2 / 3 decisions | 2 / 3 decisions |

Independent anonymous review found that both resume episodes **did ask numeric resume precedence**, despite the keyword matcher not delivering its numeric answer. Asked decisions and actually answered decisions must therefore remain separate. The decision ledger also does not represent every possible user choice; extra questions can be useful or unnecessary depending on their consequence. See the full task-local [generated interviews](INTERVIEWS.json) and independent review for those judgments. These are not real-user satisfaction measurements or answer-dependent implementation trials.

The [independent review](small-anonymous-review.md) inspected all eight anonymous production packets and all four interviews. Its [JSON](small-anonymous-review.json) binds all 36 packet files; the integrating agent verified its source locations and twelve quoted excerpts before publication. Policy labels and grades were withheld by instruction, not OS confinement; style could reveal clues. The native Codex reviewer's actual model was unobserved. This is one fresh qualitative reviewer, not a correctness vote or a model ranking.

It also found a numeric-only CLI requirement miss in C08 (original guidance, PR40 repeat 2): the patch accepts `--soft-phase-budget-seconds off` through a resolver intended for runtime disabled values. That artifact passed the primary PR40 tests, which omit this spelling. The integrating agent retraced the resolver and parse path and confirmed the permissive branch; the review used a narrow extracted-function check, not a live provider run. This is another coverage gap, and the original primary pass is retained. The review did not identify the executed stale-work guard defect in its bounded inspection; its absence of a finding cannot override the observed counterexample.

## Effort and measurement limits

Across four assigned implementations, original guidance used 116 observed operational tool calls and 733.06 aggregate inference-stage seconds; 0.8 used 115 calls and 615.57 seconds. Reported implementation cost estimates are available for three attempts in each arm: USD 2.5144 and USD 2.0972 respectively. Both timeout estimates are missing, runtime cost basis is unknown, and actual subscription charges were not observed. These incomplete estimates do not establish savings. Equal effort labels also do not establish equal compute.

The two historical tasks were chosen because an earlier prompt bundle lost on them. They are familiar, purposively selected weakness cases with two repeats, not a fresh representative sample. One additional pass is too little evidence for a general accuracy claim. This pilot does not measure Haiku routing, cross-provider review, difficult-task completion over long budgets, autonomous recovery or maintainability across a population of PRs. The independent source review is qualitative evidence and cannot substitute for executed behavior checks.

## Proof and conclusion

- [Machine-readable results](RESULTS.json): all eight implementations, four interviews, supplemental observations and post-review anonymous mapping.
- [Exact production patches](patches/): byte-identical submissions, including failures and timeout snapshots. Candidate-added tests were outside the owner grader's trusted tests.
- [Inputs and inventories](INPUTS.json): original-baseline lineage, file hashes/modes, runtime, seals, packet hashes and analysis timing.
- [Independent prospective preflight](PREFLIGHT.json): restart/interrupt retention, missing-component/peer boundaries and grader controls. Its `prior_registration_file_sha256` label refers to the original 48-study seal; `INPUTS.json` separately identifies the initial pilot seal. Raw review bytes are preserved.
- [Closure](CLOSURE.json): all assigned identities retained; current source, patches, requests, streams and oracle outputs bound; all twelve interview rounds reconstructed. This is local current-byte custody, not proof of absolute continuous immutability. Raw provider/authentication logs remain private.

The result supports a limited statement: **0.8 did slightly better on this selected primary check, and still falls short on a broader routing requirement. A broad improvement over the original remains unproven.** The next useful engineering change would target the demonstrated owner/turn boundary and clarify intake stopping criteria; these findings have not been implemented or counted as new wins in this cohort.

Forum input used before execution: “Audit the instruction reading path and induced work, not just Markdown size” (post `1d1891c0-600d-4320-a81f-07c6857c88a5`). It informed measuring observed work and fixed-task correctness rather than treating shorter guidance as proof. The explained feedback receipt was saved.
