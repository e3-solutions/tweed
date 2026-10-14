# PR replay task curation

Six tasks replay specified behaviors from real merged public `e3-solutions/tweed` PRs. These are bounded behavior slices, not claims that a solver reimplemented every change or passed each historical PR's entire test suite. GitHub PR metadata provided the immutable base/head/merge SHAs in [selection.json](selection.json).

| Task | Behavioral requirement | Sealed checks | Base | Accepted head |
| --- | --- | ---: | ---: | ---: |
| PR 32 | Route only the coordinator's completion; preserve legacy notifications | 5 | 1 | 0 |
| PR 31 | Persist usable continuation after soft-budget failure/interruption | 3 | 1 | 0 |
| PR 40 | Disable budgets through CLI, environment, resume and checkpoint values | 7 | 1 | 0 |
| PR 34 | Preserve review and existing publish identity during reconciliation | 2 | 1 | 0 |
| PR 39 | Track native ownership and attempt terminal cleanup despite child failure | 2 | 1 | 0 |
| PR 35 | Status/update and selected release-integrity failures | 6 | 1 | 0 |

Exit codes above come from the same sealed evaluator on each task's defective base and accepted production changes. Tests use real Python execution, temporary files/checkpoints, local Git installations, and deterministic protocol fixtures. No provider, Linear, or GitHub service is contacted during acceptance evaluation. PR 35 uses six selected updater cases from a larger suite; PR 39 covers the native lifecycle part of a larger orchestration change.

The first PR 32 upstream regression test passed on both base and head. It was rejected as insufficient discrimination. Independent thread/turn routing cases now fail the base with behavioral assertions and pass the accepted head. PR 33 was excluded before solver trials because its change consisted of product guidance and textual assertions. No solver outcomes were used to select or adjust these checks.

The final oracles accept two deliberately different but behaviorally equivalent implementations: renaming PR 40's new disable-choice constant and PR 39's private ownership cache throughout production code both remain GREEN. PR 31 drives CLI receipts and durable continuation instead of assuming the accepted implementation's helper return shape. PR 34 accepts extra context fields; updater error messages are not pinned to incidental wording. Required external flags, environment values, output fields and compatibility behavior are explicit in each task requirement.

## Reproduction

The builder runtime used for byte-identical oracle extraction is Python 3.14.7 on macOS. A local clone must contain the pinned commits; `--fetch-missing` optionally fetches missing public commit objects. Never prepare tasks inside a solver workspace.

```sh
python3 -B docs/research/2026-10-confidence/pr-benchmark/tasks/prepare.py \
  --repository . --output .confidence/benchmark/curation/replay --controls
python3 -B docs/research/2026-10-confidence/pr-benchmark/tasks/check_boundary.py \
  --output .confidence/benchmark/curation/boundary-controls.json
```

Use a fresh output directory: the builder refuses to overwrite snapshots. It exports complete pinned archives without original `.git`, autoload directories, or root agent instructions, preserving product workflows and packaged Bonaparte product skills. The solver receives base source, original visible tests, task requirements and production scope. It receives no accepted head, patch, PR body, sealed oracle path or historical Git objects. A fresh one-commit Git fixture can support local tests/source binding without recovering original history.

`source_sha256` uses sorted relative paths, permission bits and SHA-256 file-content digests; the algorithm is recorded in selection metadata. The runner's raw-content tree digest is a distinct convention and should be recorded separately, not compared as the same hash. Sealed test/config/runner hashes cover the generated oracle tree. Full source archives, raw controls and execution transcripts remain in ignored output paths.

## Grading boundary

The grader reconstructs a clean pinned base, copies declared regular nonsymlink production files and permitted new Python helpers, restores original baseline tests, then overlays sealed checks. Candidate edits to visible tests do not affect acceptance. A control replacing every visible test with an immediate successful exit still yields RED for the defective base.

All Git preparation and candidate/test execution occur under a macOS filesystem/network sandbox with a minimal credential-free environment. The child can read the grading workspace, scratch area and required system runtimes; it cannot read other snapshots, oracle storage, home credentials or arbitrary outside files. Original tests and the sealed entry point are immutable. Network access is denied. Controls verified outside-file read/write, symlink read, immutable-file writes and network refusal, while scratch writes succeed. Submitted symlink production files are refused before copying.

Only regular new root `.py` helpers that do not shadow standard-library/test-framework modules are admitted. The production scope and helper allowance are part of the task specification. Rejected or missing artifacts remain failures; a process's completion declaration is never the grading verdict. MacOS-only isolation, this small same-repository corpus, deterministic service fixtures and selected behavioral coverage limit generalization.

Focused visible test commands exclude installation tests requiring intentionally unavailable original Git history. The acceptance evaluator is independently sealed and may exercise cases beyond those visible commands. Freeze task/requirement/oracle hashes before the first solver trial, and do not tune against solver results.
