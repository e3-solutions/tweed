# Prospective CSV clarification for a future run

This is a future fixture/specification correction, not another executed comparison. Current TASKS, owner checks, scores and PRE-INFERENCE manifest remain unchanged. No additional solver, owner rerun or provider call was made.

For the constructor slice, reject **non-None noniterable** fieldnames with TypeError. Preserve `DictReader(None)` header inference and historical `DictWriter(None)` constructor behavior, matching the accepted reference. Add explicit independent checks for both None cases before a future run, along with the existing iterator, mutable-sequence, extras/missing-column and quoting boundaries. If rejecting writer None is desired instead, define it as a separate behavior change with its own accepted authority; do not silently reinterpret this historical PR.

All future driver actions must receive an absolute `--study` path, including external grading-source paths. Keep artifact acceptance, provider delivery, tool/data custody and controller execution separate. Source-preserving setup corrections do not count as model repairs.
