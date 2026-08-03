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
to zero. The configured deterministic adapter's production latency is not
measured because no officially authenticated atomic adapter is installed.

## Snapshot replay

The recorded replay of snapshot/artifact/packet construction took 15.712 ms for
all three phases; this local transform timing naturally varies by machine.

| Phase | Frozen snapshot | Old initial prompt | New initial prompt | Referenced artifact bodies | Artifact store |
|---|---:|---:|---:|---:|---:|
| Scope | 1,210 B | 1,848 B | 2,292 B | 708 B | 11,208 B |
| Implement | 17,384 B | 18,026 B | 2,656 B | 18,307 B | 46,810 B |
| Review | 25,324 B | 25,963 B | 3,052 B | 26,128 B | 64,515 B |
| Total | 43,918 B | 45,837 B | 8,000 B | 45,143 B | 122,533 B |

Initial phase prompts shrink 82.5% overall and never repeat the complete issue
or report payload. Referenced bodies remain available by path/hash and are read
only when needed. The artifact-store total includes the exact frozen
description, workflow, manifest packet, separate handoff bodies, and evidence;
it is private local disk I/O, not model prompt input.

## Cache behavior

The hermetic evidence-runner test records a miss on first execution, a hit only
for an identical complete key, and recomputation after a dependency digest
change. Independent tests invalidate the key on repository identity, argv,
dependency/lockfile bytes, configuration bytes, declared environment values,
tool/runtime versions, and artifact hashes. Missing or uncertain inputs fail
closed. Reviewer reasoning and post-repair targeted re-review are not cached.

## Assurance parity

The fixture and current workflows retain all five review axes, the three
implementation review axes, triggered specialists, non-authoring targeted
re-review after repairs, full relevant test/type/lint/build checks, zero
unresolved material findings, clean commit/worktree checks, and scope-to-diff
audit. Stage 1 does not remove or combine reviewers.
