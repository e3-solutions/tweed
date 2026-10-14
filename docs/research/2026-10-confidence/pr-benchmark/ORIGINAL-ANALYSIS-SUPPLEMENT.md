# Original study descriptive supplement

The registered analysis is unchanged. These results separate accepted artifacts from accepted artifacts with a complete final declaration and no listed gaps. All 84 scheduled trials remain visible; two external interruptions stay unknown.

| Arm | Accepted artifacts /12 | Accepted + complete declaration /12 | Unknown interrupted | Acceptance possible range |
|---|---:|---:|---:|---:|
| bounded_repair | 2/12 | 1/12 | 1 | 2–3/12 |
| compact_routing | 4/12 | 0/12 | 0 | 4–4/12 |
| counterexample_first | 4/12 | 0/12 | 0 | 4–4/12 |
| current_cp_06 | 4/12 | 1/12 | 0 | 4–4/12 |
| dependency_slicing | 3/12 | 0/12 | 0 | 3–3/12 |
| independent_review | 4/12 | 0/12 | 0 | 4–4/12 |
| original_cp_05 | 3/12 | 0/12 | 1 | 3–4/12 |

Unknown interrupted outcomes are not observed failures. The ranges assign only logically possible 0/1 outcomes to the missing records; they are not imputed scores, probabilities, or confidence intervals. A positive observed alternative-minus-baseline delta can shrink by 8.33 percentage points if the missing original outcome would have passed. Both bounded-repair and original have one unknown, allowing their difference to shift in either direction.

The stronger declaration metric requires scope-valid acceptance, valid harness metadata, `declared_complete=true`, and exactly `remaining=[]`. It does not establish that every proof packet or peer call completed; proof-packet sufficiency remains unassessed.

Complete-pair secondary comparisons exclude a task/repeat pair only when either primary acceptance field is unknown. They preserve observed harness-invalid nonsuccesses, average repeat differences within each task, and then weight the six task clusters equally. Each alternative has 11 complete pairs; PR35 contributes one repeat, and the other tasks contribute two. This selected complete-case view is descriptive. Its available-repeat task mean is a different quantity from the fixed 12-trial identification bounds, so their numerical values must not be treated as interchangeable estimates.

| Alternative | Complete pairs | Available-repeat mean task delta | Fixed 12-trial delta identification bounds |
|---|---:|---:|---:|
| bounded_repair | 11 | -8.33 pp | -16.67 to +0.00 pp |
| compact_routing | 11 | +0.00 pp | +0.00 to +8.33 pp |
| counterexample_first | 11 | +16.67 pp | +0.00 to +8.33 pp |
| current_cp_06 | 11 | +0.00 pp | +0.00 to +8.33 pp |
| dependency_slicing | 11 | -8.33 pp | -8.33 to +0.00 pp |
| independent_review | 11 | +8.33 pp | +0.00 to +8.33 pp |

| Separate posthoc workflow audit | Registered oracle | Workflow audit |
|---|---:|---:|
| tweed-pr32 | 3/14 | 4/14 |
| tweed-pr40 | 2/14 | 14/14 |

These workflow audits were developed after observations and cover all 14 identities for each audited task. They diagnose comparator limitations and do not replace original scores or prove protocol efficacy. See the separate workflow and budget/resume audit reports for their behavioral scope.

Exact input file hashes, complete-pair counts/differences, missing-outcome bounds, changed workflow-audit identities, and definitions are recorded in `ORIGINAL-ANALYSIS-SUPPLEMENT.json`. The six historical PR clusters and two repeats do not justify a general claim of increased accuracy or autonomy.
