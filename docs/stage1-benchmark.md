# Stage 1 efficiency benchmark

Fixture: immutable, sanitized COR-3270 run topology and archived aggregate task
metrics from 2026-08-03. Source snapshot SHA-256 digests, byte lengths, section
topology, run IDs, expected stable output, and transport/task counts are committed
in `benchmarks/fixtures/cor3270.json`; transcripts and human-readable issue content
are intentionally excluded. The benchmark performs no Linear write, restart,
deployment, or fixture-repository mutation.

Reproduce the report without touching Linear or the fixture repository:

```sh
uv run benchmarks/cor3270_stage1.py
```

The immutable source run IDs are `tw_26fabe4180d04027` (scope),
`tw_952ed09e00554161` (implementation), and `tw_e26ffa33f007461d`
(review). Stable replay drift exits nonzero; only local transform timing is
excluded from comparison.

## Recorded baseline

The preserved feature lifecycle ran from `16:40:16.599Z` through
`17:56:39.333Z`: 4,582.734 seconds wall time. Its archived task snapshots
contain 38 model tasks: 23 phase coordinator/agent tasks and 15 tasks used only
for Linear transport (1 create, 8 complete reads, and 6 update/CAS attempts).
Those transport tasks consumed 1,652.222 task-seconds. Exact aggregate model
token use is unavailable: the archived counters are cumulative and cannot be
attributed reliably, so this report does not estimate it.

Holding all 23 reasoning/reviewer tasks fixed and replacing only transport
projects 2,930.512 seconds wall time, a 36.1% reduction. Total model task count
falls from 38 to 23 (39.5%); model-powered Linear transport tasks fall from 15
to zero. The bundled production adapter's live Linear latency is not measured
because `LINEAR_API_KEY` was not configured. No connector credential was
extracted and no live result is fabricated. Hermetic journal/adapter operations
are covered by the complete local suite and committed fixture replay.

## Snapshot replay

The replay constructs production-shaped adapter snapshots (including issue,
team/project, content and snapshot digests) alongside the preserved materialized
phase descriptions. It measures the packet/artifact boundary, not a live adapter
round trip. Local transform timing is emitted by the command and varies by machine.

| Phase | Frozen snapshot | Old initial prompt | New initial prompt | Referenced artifact bodies | Unique artifact bodies |
|---|---:|---:|---:|---:|---:|
| Scope | 1,210 B | 1,848 B | 2,407 B | 708 B | 13,445 B |
| Implement | 17,384 B | 18,026 B | 2,801 B | 18,307 B | 65,233 B |
| Review | 25,324 B | 25,963 B | 3,227 B | 26,128 B | 90,891 B |
| Total | 43,918 B | 45,837 B | 8,435 B | 45,143 B | 169,569 B |

Initial phase prompts shrink 81.6% overall and never repeat the complete issue
or report payload. Referenced bodies remain available by path/hash and are read
only when needed. `artifact_store_bytes` is the sum of unique content-addressed
artifact body bytes, including frozen descriptions/transport snapshots,
workflows, handoffs, and evidence. It excludes manifest JSON, immutable manifest
snapshots, phase-packet bytes, and filesystem overhead; it is not model prompt
input.

The current hermetic replay is an actual local measurement, not a projected
workflow run: 0 child/model tasks, 0 model-powered Linear transport tasks, 0
live Linear requests, 8,435 prompt bytes, 45,143 referenced-artifact bytes, and
169,569 unique content-addressed artifact body bytes. Its latest transform wall time is emitted by the
command because machine timing varies. A full lifecycle wall time and child-task
count remain explicitly projected from the preserved baseline until an
authenticated disposable canary can run. Exact attributable token accounting
is unavailable and remains `null`, not estimated.

## Cache behavior

The hermetic evidence-runner test records a miss on first execution, a hit only
for an identical complete key, and recomputation after a dependency digest
change. Independent tests invalidate the key on repository identity, argv,
dependency/lockfile bytes, configuration bytes, declared environment values,
tool/runtime versions, execution timeout, and artifact hashes. Missing or uncertain inputs fail
closed. Reviewer reasoning and post-repair targeted re-review are not cached.

## Assurance parity

The fixture and current workflows retain all five review axes, the three
implementation review axes, triggered specialists, non-authoring targeted
re-review after repairs, full relevant test/type/lint/build checks, zero
unresolved material findings, clean commit/worktree checks, and scope-to-diff
audit. Stage 1 does not remove or combine reviewers.
