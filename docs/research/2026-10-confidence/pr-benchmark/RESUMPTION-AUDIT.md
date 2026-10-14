# Original study interruption and supervised continuation

The user-turn interruption stopped the original coordinator and grader. This is
an operational interruption, not a reason to rerun unsuccessful model trials.
The frozen 84-trial denominator, original prompts, task snapshots, toolkit
packages, model, effort, budgets, execution code, and grading code are retained.

The sealed inventory at **2026-10-12 16:57:06 UTC** contained 61 completed raw
receipts, two preexisting trial directories without receipts, and 21 trial
directories that had never been created. The two interrupted identities are:

- `tweed-pr35--original_cp_05--r2`
- `tweed-pr35--bounded_repair--r2`

Those identities remain unknown and are not retried. Empty directories do not
establish whether a provider emitted a response; their model-emission state is
also unknown. They remain in the frozen 84-trial analysis denominator. No cost,
completion, acceptance, or elapsed-time value is invented for them.

`supervised_resume.py` invokes the immutable original `run_trial` for only the
21 never-started identities, in the original frozen schedule order, with three
workers. Each directory is created exclusively before invoking the runner; an
existing directory is refused. The inventory seal is also exclusive, preventing
a second launch from silently reusing this continuation plan. Detached process
launching makes ordinary tool-session closure independent of the coordinator.

Before launch, the coordinator verified all registered request digests, source
and oracle snapshots, archive/package identities, protocol/manifest bytes, and
runtime versions. Python remains 3.14.7 and Claude Code remains 2.1.285, with
requested `claude-opus-5-5` at medium effort. The registered runner SHA-256 is
`1f5e9ab2e5f0823a34c8f637ae08b4b3e7e1d1ac7bbbf5aab64ab79c95288fb8`;
the unchanged grading adapter SHA-256 is
`bcec860d709ddbe3c3566fb7bcdc86805b4a3e5c69131167b7743c91cbb2a007`.

The unchanged idempotent grading watcher is restarted. Previously graded raw
receipts are matched to their recorded digest; no solver receives grading
feedback. The previously ungraded 61st receipt receives its first grade. A
coordinator-launch race placed its initially empty `grader.stdout` and
`grader.stderr` files in the inventory before that first grade finished. Those
grading-output files are an explicit preservation exception; all preexisting
raw receipts, model transcripts, production submissions, source snapshots, and
completed grade records must retain their original hashes. This exception
changes neither a solver artifact nor a grade.

Eight focused supervisor controls pass: empty existing directories are treated
as interrupted, interrupted model emission stays unknown, raw receipt hashes
are captured, symlink material is refused, and a mismatched frozen code hash is
rejected before importing it. Additional regression checks permit only pending
first-grade output changes, reject modifications of completed grade outputs,
and reject raw receipt changes even while the first grade is pending. Run with:

```sh
python3 -B -m unittest discover \
  -s docs/research/2026-10-confidence/pr-benchmark \
  -p test_supervised_resume.py
```

The continuation occurs later than the initial batch. CLI versions and requested
model/effort stay fixed, but the provider's internal deployment is not observable
or pinned; temporal service drift remains a limitation. The interruption and
resumption do not establish comparative efficacy.

Private evidence is retained under `.confidence/benchmark/study/resumption/`
and `resume-launch/`; it contains the inventory, launch and per-trial events,
artifact hashes, and operational logs. Raw model content and local absolute
paths are not published.

The continuation closed at **2026-10-12 17:25:05 UTC** with 82 raw receipts,
82 independent completed grades, all 84 normalized scheduled rows, and the two
interrupted identities still unknown. All 21 selected continuations started
exactly once. The final independent audit found zero preservation violations;
its only permitted exception was the previously empty first-grade stdout for
`tweed-pr35--independent_review--r2`.

The executed coordinator's original final guard was overbroad: it included that
pending grade output in immutable material. It therefore exited nonzero after
finishing all 21 trials. The executed source is retained privately with SHA-256
`836db3545cc16285ba23feb5c5103f0d2b8b0ab73500828c0cf42ea751349024`.
After execution, the guard was corrected to distinguish only pending first-grade
stdout/stderr from immutable solver evidence and completed grades. The corrected
guard passes against the sealed actual inventory, and the eight controls above
pass. No solver trial or completed grade was rerun for this correction.

The final independent audit is recorded separately from the overbroad original
completion guard; neither historical record is overwritten. The original
runner, grader, requests, and scoring analysis retain their frozen hashes.
