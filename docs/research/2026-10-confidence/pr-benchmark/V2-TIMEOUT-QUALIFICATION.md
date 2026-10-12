# Preserving timeout receipts through macOS group cleanup

The final V2 helper reaps its direct child before escalating `SIGKILL` to the
original process group. This addresses an actual reproduced infrastructure
failure and does not change a model outcome into success. Timed-out calls retain
unknown completion even when the CLI exits cleanly during termination.

Two actual short Astra calls, writable and readonly, reproduced `PermissionError`
after the original helper sent `SIGTERM`, waited its grace interval and attempted
`SIGKILL`. A direct adapter invocation retained the traceback: the exception came
from `cleanup_group` at group escalation. A narrowly scoped diagnostic inspected
only the owned process group after the refusal; its sole member was the unreaped
zombie direct child. After reaping, the group no longer existed. A separate local
`sleep` process reproduced the same sequence: escalation refused before `poll`,
then returned process-not-found after `poll` reaped the child.

This mechanism can explain the historical timeout receipt loss. The first block
recorded the same permission-error class but not those tracebacks, so this does
not authenticate the cause of every historical instance. The separate historical
disk-space error remains unexplained. No old receipt, grade or frozen helper is
rewritten.

`hybrid_process_v2.py` changes only the V2 controller's imported helper. It calls
`poll` after the grace period, still sends `SIGKILL` to stop surviving group members,
reaps a live direct child after escalation, and preserves real permission errors.
It neither ignores all `EPERM` errors nor scans or kills unrelated processes.
The same helper is installed into the separate V2 grader's private runner.

Thirteen controls pass: four new reaping/refusal cases plus the nine existing
original-group lifecycle cases against the updated helper. They exercise successful
leaders, cooperative timeout, SIGTERM-ignoring descendants, concurrent ownership,
dummy Claude/Codex launchers, captured stream hashes, and the real `setsid` escape
limit. An escaped descendant can still survive; no full descendant containment is
claimed. Process IDs can be reused and endpoint hashes cannot detect every transient
write; the exercised group scope is the limit of this evidence.

Two fresh actual five-second Astra controls after the fix preserved full provider
receipts: `timed_out=true`, `status=timeout_unfinished`, `declared_complete=null`,
qualified transport and original-group cleanup. The CLI returned exit zero while
being stopped, which did not override the timeout flag. These are infrastructure
controls with zero historical-task efficacy assignments. Their retained summary
SHA256 is `e220d7735f31c15757232b9a62c5f6a1038d51d1bf475371c4427468ec984099`.
The failed pre-fix summary SHA256 is
`12dab7d4a92ebfe8dda3b9a4d37ef0c061fc22a42f7f1f633c9d7d42592c8196`.

Run the local controls:

```sh
python3 -B -m unittest discover \
  -s docs/research/2026-10-confidence/pr-benchmark \
  -p test_hybrid_process_v2.py -v
```

The full hosted staged toy was separately rerun against the updated wrapper and
helper before V2 historical tasks. Earlier successful-normal-path toys do not
qualify this changed cleanup implementation.
