# Public projection of a closed schedule

`export_completed_study.py` supports complete schedules that contain interrupted
or unstarted assignments. It does not change any registered scoring rule. The
older `export_results.py`, graders, statistical analyzers, and raw receipts are
unchanged.

Publication requires a separate closure manifest containing the exact schedule
hash, closure date, explicit stop reason, private sealed-inventory path and
hash, and classifications for exactly the missing assignments. That inventory
must account for the entire scheduled cohort, bind existing raw and graded
receipt bytes and production patches, and bind captured provider requests and
stage receipts. A later added or removed provider request/receipt fails
validation. This is an operational closure, not proof that absent assignments
ran or were acceptance failures.

For existing observations, the aggregate row must equal the graded receipt's
`normalized` row exactly, and the graded receipt must bind the actual raw receipt
hash. Published patch bytes must match the recorded digest and use only the
trusted raw receipt's submitted production paths. Patch headers cannot name
proof directories or absolute paths. A private host path anywhere in a patch
refuses publication; the exporter does not silently rewrite the patch and claim
its original hash.

Missing assignments retain null task grade, completion, cost, time,
interventions, harness eligibility, false-completion and error-count evidence.
Their assignment states distinguish `interrupted_no_receipt` and
`never_started`. They remain in the published schedule. Existing known cost
subtotals are retained separately; null actual cost is never replaced by zero.

The public JSON uses explicit field projections. It omits source paths,
configuration argv, free-form errors, model summaries, remaining-work prose,
provider payloads, transcripts, and reasoning. Stage usage keeps recognized
numeric token counts; other usage text is omitted. V2 qualification retains
known/unknown qualification, tool inventories, resource-handler differences,
local process-result hashes, readonly flags, normalized source-binding
digests and lifecycle evidence, while removing actor cwd and config paths. Both
raw adapter qualification and independently derived normalized qualification
remain distinct. Null facts remain null; malformed source-digest text is redacted
and explicitly flagged as invalid rather than published as a digest. Actual provider errors in the V1 retrospective supplement are
reduced to recognized exception classes; the original detailed supplement stays
private and unchanged.

The V1 retrospective inventory qualification is published as a separate file
with its source hash and receipt bindings. It cannot overwrite registered
primary harness flags or grades. Missing assignments' supplemental success
eligibility is null in the public projection. This field concerns verified
eligibility, not an assertion that an unstarted task failed.

Twenty-one synthetic publication controls cover full-schedule accounting, unknown
preservation, redaction, exact closure coverage, raw/grade binding, stale
aggregates, post-seal changes, schedule changes, production-only patches,
private-path refusal, symlink refusal, separate retrospective supplements, and
V2 qualification hashes/resource differences, explicit V2 grading filenames,
and optional independent completion-audit binding.

## Operational commands

Seal only after the coordinator and grader are stopped and the intended cohort
has reached its documented operational end:

```sh
python3 -B docs/research/2026-10-confidence/pr-benchmark/export_completed_study.py seal \
  --study STUDY --schedule SCHEDULE \
  --inventory NEW_PRIVATE_INVENTORY --closure NEW_PRIVATE_CLOSURE \
  --reason 'Documented reason for operational closure'
```

Export the exact full schedule:

```sh
python3 -B docs/research/2026-10-confidence/pr-benchmark/export_completed_study.py export \
  --study STUDY --schedule SCHEDULE --closure PRIVATE_CLOSURE --output PUBLIC_DIRECTORY
```

For V2, select `--graded-filename v2-graded-receipt.json` during both
closure and export; that explicit choice is pinned in the closure. Original and
V1 cohorts use `graded-receipt.json`. Supply `--completion-evidence` during
closure to pin an independently successful completion audit.

For V1, also supply `--supplement` with its private retrospective inventory
qualification. No V2 closure is created while V2 is running. The closure command
cannot independently prove that provider processes have stopped; its explicit
stop reason must be backed by coordinator evidence. This limitation is separate
from the file-integrity checks.
