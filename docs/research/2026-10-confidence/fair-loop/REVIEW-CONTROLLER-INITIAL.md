# Independent authored-controller preflight review — initial

Verdict: **NOT READY for task inference.** Read the actual Opus-authored core/tests/README and unchanged native control receipts. No model calls, source edits or broad test reruns. This is a controller review, not product solving evidence.

The author honestly marked provider wiring incomplete and sandbox control skipped. Native execution resolves that skip to a baseline failure: Python print(1) exits -6 with no stdout/stderr. Five controls pass, but control 4 does not establish confinement. Preserve the author and native receipts; do not report six qualified controls.

Smallest required correction contracts:
1. **Launch composition:** run_stage needs the assigned cwd and existing qualified adapter/MCP-service callback; use the established sandbox profile/support-read composition plus current task target denies. A bare provider Popen does not wire the controlled tools. Qualify baseline success before any negative denial result.
2. **Settlement:** cleanup must kill/reap surviving owned descendants even after the parent exits. group_alive or unknown cleanup prevents ledger settlement and next dispatch. Close retained streams and capture current source/policy while still holding the global lock; persist those bindings before settlement. An exception leaves a durable unsettled record.
3. **Manual clearing:** settle_explicitly currently accepts any note and can clear a live/unresolved admission without taking the global lock. Remove it if unnecessary; otherwise verify owned-group absence plus retained output/source proof under that lock. No note alone clears active ownership.
4. **Continuation qualification:** both triggers require observed actual model, registered permissions/tool use, current bound grade, stable source/policy and known clean settlement. Current artifact-gap branch accepts receipt={} and source_stable=False. Deadline init-tools superset alone does not qualify tool requests; reconcile declared inventory/allowed permissions with actual requests. Unknown cannot authorize retry.
5. **Raw stream custody:** preserve actual terminal even when the runtime deadline fires; timed_out remains true independently. parse_stream must record/reject invalid JSON, duplicate init/result and model/session inconsistencies rather than skipping or selecting the last terminal. Missing terminal is not fabricated into success.
6. **Inputs/feedback:** per-cell seal is sufficient, but recompute authentic base material as well as task declarations/policy bytes after prepare; a stored expected SHA is not current source verification. Forward complete safe required rows and qualified delivery gap, omitting private temporary owner paths. module_origin imports actor code without confinement: omit it from execution or run through the qualified sandbox; the independent grader already owns binding.

Keep the six bounded controls, strengthened at these boundaries: actual lock contention; forced timeout with a TERM-resistant descendant and retained outputs; after-prepare material mutation; composed MCP-child baseline plus outside/private/target/network denial; actual local module provenance; qualified continuation admission and durable max-one claim. No new task panel or controller framework is needed.

Candidate snapshot b84c876c9ab3b8ade74a920fd9f7c5e27ff1b7989357236990de9616a0a7a587 already permits ordinary tests for changed requirements, protects independent checks/unrelated regressions and removes a fixed retry count. Its default loop duplicates later sections and the no-new-facts retry rule appears three times; lean trimming is a prospective usability correction, not a retrospective score/cap change.

Bound authored SHA256:
- controller.py: `1b83296c2d904551aaa12dbe93301f1102c5d91d18fdf57f9e1c7d4859056dee`
- tests/test_controls.py: `548d27cb8aa6c30e5723640e8893e603b93b5a158cefc979f3e71849d357480f`
- README.md: `28cb0fe24cd925eb628821b156c23b22d413f7e9ba60192b7881718ff8226397`

The first development deadline remains a partial author delivery; the following qualified author response expressly left implementation gaps. Neither record is a task outcome or a complete launch qualification.
