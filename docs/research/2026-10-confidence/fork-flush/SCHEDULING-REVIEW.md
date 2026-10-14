# Independent scheduling and scoped-behavior review

**Registered concurrency fidelity FAIL: three active model calls overlapped.** Candidate size disqualification independently remains; no promotion or confirmation. PR45 results are behavioral diagnostics, not fully comparable promotion/timing evidence. No causal effect on latency, timeout or accuracy is established.

Method: retained call/request.json mtime is immediately before Popen in the sealed caller; stage wall_seconds gives approximate process-call end. Raw assistant timestamps and actual command-request mtimes independently corroborate liveness. All inspected raw streams match stage stream hashes. Request-mtime intervals are approximate, not exact provider compute durations; no task/model/grader calls were made by this reviewer.

| Stage | Request mtime UTC | Approximate end UTC | Wall seconds |
| --- | --- | --- | ---: |
| tweed-pr26--incumbent/solve | 01:10:32.694 | 01:12:50.643 | 137.949 |
| tweed-pr26--branch-a/solve | 01:10:32.693 | 01:13:02.789 | 150.095 |
| tweed-pr26--branch-b/solve | 01:12:51.572 | 01:14:58.460 | 126.888 |
| tweed-pr45--branch-b/solve | 01:14:59.328 | 01:17:24.864 | 145.536 |
| tweed-pr45--incumbent/solve | 01:14:59.328 | 01:17:29.474 | 150.145 |
| tweed-pr26--branch-a/repair | 01:15:30.031 | 01:16:14.508 | 44.477 |
| tweed-pr45--branch-a/solve | 01:17:26.810 | 01:19:31.964 | 125.154 |

All rows are 2026-10-14 UTC. A PR26 repair's approximate 01:15:30.032–01:16:14.508 interval lies completely inside PR45 B and incumbent solves: about 44.48 seconds with three calls, exceeding global max 2. Conservative raw assistant spans overlap for 41.415 seconds (A repair 01:15:32.756–01:16:14.171, inside both other spans). All three performed retained command requests during that window. This is actual overlap, not an inference from merely queued tasks.

Pause at 01:16:43.746 and resume at 01:17:07.889 UTC both followed A repair completion. Pausing the dispatcher then did not pause the already-active children and could not prevent or undo the overlap. Do not credit it as prior concurrency enforcement. Further repairs may follow all main calls within max 2; no rerun or rule/source change is warranted merely to obtain comparable or better outcomes.

Independent product evidence, kept separate:

- Rebound seven existing evaluator observations (six main outputs plus A PR26 repair): actual stdout/stderr digests, raw header, output digest and current saved source digests agree; frozen positive/negative and baseline checks ran with verified setup. This is artifact revalidation, not newly executed grading.
- PR26 incumbent and B current scoped gates pass with qualified deliveries. A first positive/negative/baseline behavior also passes, but protected old-test-file scope fails and main timed out without a terminal. A repaired source passes all scoped gates with a qualified repair delivery; its original missing main metadata remains unknown. First and repaired production patches are identical, so this repair does not establish a product-code improvement.
- A added 54 lines of meaningful boundary/Unicode/CLI regression coverage to existing tests/test_bonaparte.py; it did not remove or weaken baseline assertions. The failure is the experiment's protected-existing-test-file constraint, not an observed product bug or bad test design. Repair restores that original file byte-exact and moves the new coverage to tests/test_receipt_line_limit.py, an allowed addition; new actor tests do not influence owner grading.
- At this snapshot, PR45 A passes scoped gates with qualified delivery; B positive/negative/baseline behavior passes but existing-test-file scope fails; incumbent scoped gates pass but its main timeout/missing terminal remains unknown. Later permitted repairs require separate current-source audit. None removes the historical scheduling violation or candidate cap failure.
- Timeout attribution cannot be inferred from this overlap or an absent terminal alone. Observed produced behavior, stage delivery, experimental scope and controller fidelity are separate judgments; neither blanket absolution nor automatic product failure is justified.

Evidence identity:
- `registration`: `977678d29bf487c356c8a257ca32eeedb69f413a7c6f576d6d5d4d6f0fbabce6`
- `caller`: `1f5e9ab2e5f0823a34c8f637ae08b4b3e7e1d1ac7bbbf5aab64ab79c95288fb8`
- `pause record`: `aa188e64b2154deb1eba2c13b9a1ac745d5c79673a819b8a94d3db31e6aaafb3`
