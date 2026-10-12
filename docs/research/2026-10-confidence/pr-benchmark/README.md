# Real PR replay evidence

The original comparison tested six proposed workflows against Confidence Protocol
0.5 on six historical public PR tasks. It produced a small descriptive difference,
not a demonstrated accuracy gain. Codex-to-Claude delegation separately worked
in actual provider calls. The first mixed-provider block had invalid transport;
a corrected block requires qualified baselines and a fresh public registration.

This directory preserves the original registrations, code and evidence rather
than silently repairing unsuccessful trials. Production patches, bound result
rows, artifact hashes and closure receipts are public. Private transcripts, tool
output, local queue paths and credentials are omitted. Research is excluded from
the installed plugin archive.

## Original comparison

The frozen study assigned 84 tuples: seven arms, six tasks and two repeats.
All arms requested exact Opus5.5 medium, with identical task source, applicable
protocol package, controlled tools and resource rules. Six interventions were
CP0.6, compact routing, counterexample first, dependency slicing, independent
review and bounded repair. Packages came from pinned Git archives; full actual
skills and their shipped toolkit were supplied, not a coordinator paraphrase.
The initial runner/grader remain byte-identical to their registration.

An operational interruption stopped the coordinator after 61 receipts. Two begun
assignments without final receipts were retained as unknown. Only the 21 never
started identities continued under the unchanged schedule and three-worker rule.
The final audit verified 82 raw/graded receipts, 84 normalized rows, 21 unique
continuations, preservation of prior solver artifacts and no retrials. One
first-grade log race was a disclosed grading-only preservation exception. See
[RESUMPTION-AUDIT.md](RESUMPTION-AUDIT.md).

| Arm | Accepted submissions /12 | Accepted plus complete declaration and no terminal gaps /12 |
| --- | ---: | ---: |
| Original CP0.5 | 3 | 0 |
| Current CP0.6 | 4 | 1 |
| Compact routing | 4 | 0 |
| Counterexample first | 4 | 0 |
| Dependency slicing | 3 | 0 |
| Independent review | 4 | 0 |
| Bounded repair | 2 | 1 |

Acceptance means the frozen selected oracle accepted a scope-valid, model-valid
submission. It does not require a final declaration. The stronger column also
requires a valid `complete=true` terminal with an empty remaining list; it still
does not establish proof-packet quality, authenticated review independence or
correctness beyond the oracle. Missing declarations are unknown, not truthful
partial reports. Coordinator task hints were absent, but an external interruption
and later resumption occurred; this is not a demonstration of uninterrupted
end-to-end autonomy.

The nominal CP0.6 difference is one extra verified submission, or 8.33 percentage
points. The entire extra submission is PR35 repeat2: CP0.6 was accepted while its
baseline assignment was externally interrupted and remains unknown. Across the
11 observed complete pairs, the CP0.6 task-cluster acceptance difference is exactly
zero. The lower-bound registered analysis has one positive task cluster and five
ties; its exact empirical six-task bootstrap interval is [0,25] percentage points.
This is descriptive only and does not resolve the missing comparison, establish
statistical significance or provide a population guarantee. Other four-submission arms also
have uncertainty spanning no improvement. Repeats do not turn six selected PRs
into twelve independent tasks.

The registered analysis treats no verified success as zero in its assigned
success count, including unknown assignments. That is a lower-bound verified
success metric, not an observed oracle-failure count. Its `observed_receipts`
field counts the 84 input normalized rows; actual final receipts number 82.
Do not edit that frozen analysis to hide the naming limitation. The separately
labeled analysis supplement reports complete-pair and missing-outcome bounds.

## Acceptance-oracle limits

Independent secondary public-behavior audits found implementation-location and
representation coupling in two old oracles. Their base/head controls had passed;
that did not establish acceptance of all valid alternative implementations.

- PR32: the frozen primary accepted 3/14, while seven public `run_phase` workflow
  cases accepted 4/14. The one disagreement was CP0.6 repeat1, which placed filtering
  in a different valid workflow location.
- PR40: the frozen primary accepted 2/14; eight public CLI/resume/storage/native
  cases accepted 14/14. Twelve candidates passed the broader public contract while
  failing internal sentinel/helper expectations in the primary.

These are post-hoc audits informed by observed outcomes. They neither replace the
registered primary results nor prove full correctness of those candidates. They
prevent presenting the old primary as a complete measure of task accuracy. A
prospective ninth elapsed-deadline case was qualified for the new mixed-provider
study only. See [workflow audit](tasks/WORKFLOW-AUDIT.md) and
[budget/resume audit](tasks/BUDGET-RESUME-AUDIT.md).

PR35 and PR39 cover registered bounded behaviors rather than their entire PRs.
All six tasks come from one repository. Historical solutions might have appeared
in model training; hiding local history and gold patches cannot rule that out.
Provider internal deployments are not pinned by a CLI version. Original nested
peer waits can consume a main episode's active deadline; this and missing terminal
costs limit conclusions about repair, review and efficiency.

## Calling Claude through Codex

Actual Astra-route Codex calls invoked `request_review`, launched a bounded
Claude Code process requesting exact Opus5.5, received its runtime-observed model
and source-bound artifact, and then continued using the returned receipt. The
peer executed checks and attempted a source write that confinement denied.
The sanitized [BRIDGE-PROOF.json](BRIDGE-PROOF.json) binds the callback, actual
peer command receipts, source endpoints and independently executed final behavior.
The final guarded callback toy also executed the real CP0.6 confidence capture.
This establishes the callback capability at that exercised boundary; it does not
establish improved task-solving accuracy.

Sol6.1 was rejected by the authorized ChatGPT CLI route in two exact availability
probes. No trial silently substituted another model. Astra was explicitly chosen
before the mixed-provider design froze. Codex's observed stream omitted response
model identity and dollar cost: its attribution stays requested-only and total
cost stays unknown. Opus model metadata was observed in the actual Claude stream.
Neither stream reveals hidden reasoning, internal weights or authenticated
statistical independence.

The mixed-provider comparison changes only peer provider at each fixed main
provider, within a common externally staged CP0.6 workflow. That estimates a
routing effect within this workflow, not the effect of native callback delegation.
Both directions and both same-provider controls are required. Distinct provider
accounts distribute authorized usage but do not merge or expand quotas.

## Mixed-provider infrastructure audit

The first 48-assignment block stopped with 19 final receipts, two interrupted
assignments and 27 never started. All 40 observed Opus stage initializations lacked
the seven workspace tools: a relative config path resolved under the actor cwd.
The historical primary grades remain unchanged, alongside the separate transport
supplement. No accuracy ranking is valid. See
[V1-INVENTORY-SUPPLEMENT.md](V1-INVENTORY-SUPPLEMENT.md).

V2 adds absolute-path normalization and per-stage transport/effective-inventory
qualification. Normal staged calls and forced timeouts are qualified separately.
A reproduced macOS zombie-group cleanup failure is addressed by reaping the
direct child before group escalation; genuine permission failures still fail.
Baseline execution also needs an empty confined home and scratch outside copied
source. These infrastructure corrections require a new seal and real staged
qualification before historical-task launch. See
[V2 registration](HYBRID-V2-PREREGISTRATION.md),
[qualification](V2-QUALIFICATION.md), and
[timeout qualification](V2-TIMEOUT-QUALIFICATION.md).

The common control is wall time, not tokens or dollars. Claude per-stage dollar
guards have no equivalent Codex dollar guard. Complete vendor tool inventories
also differ: Codex retains three resource handlers and only offline declaration
is observed, while Claude exposes a live initialization plus StructuredOutput.
Process groups do not contain descendants that detach with `setsid`. No complete
descendant containment, absolute artifact immutability or strict seven-tool parity
is claimed.

## Inspect and reproduce

Original public results are in [results/original-comparison](results/original-comparison);
invalid first-block results are in [results/hybrid-v1](results/hybrid-v1).
`artifact-hashes.json` binds each production patch to its raw and graded receipts;
closure files preserve the full assignment roster and missing states. The private
raw evidence remains locally available for authorized audit.

Stored `.patch` evidence is exempt from whitespace cleanup and line-ending
conversion under a narrow `.gitattributes` path rule. Unified-diff blank context
markers are literal spaces; trimming them would change the proof bytes. All101
original/V1 production patch hashes survived the CI repair unchanged. A temporary
repository control rejected an ordinary source whitespace error while accepting
the byte-exact patch fixture. Other source/document whitespace checks remain
enabled. [Git attribute semantics](https://git-scm.com/docs/gitattributes#_checking_whitespace_errors).

Run local benchmark controls on the pinned macOS runtime:

```sh
python3 -B -m unittest discover \
  -s docs/research/2026-10-confidence/pr-benchmark -p 'test_*.py'
```

Rerunning hosted trials spends provider usage and produces a new experiment; it
cannot reproduce an identical model response or overwrite this cohort. The frozen
task preparer pins historical revisions and restores trusted acceptance tests for
production-only submissions. Deletion of configured baseline production files is
explicitly unsupported in the new projection and produces unknown grading rather
than letting an overlay silently restore a deleted file.
