# Complex tasks and autonomous proof

Use this overlay for interdependent work, consequential handoffs, or tasks spanning
multiple context windows. Keep ordinary work on the shorter core workflow. The
native harness executes actions; Confidence Protocol records and challenges proof.

## Decompose around observable behavior

Write a small set of obligations that can each be rejected by a concrete check.
Include the real user interface and consequential external boundaries. Give one
owner each edit scope and distinguish implementation, proof design, and review.
Parallelize independent exploration or isolated components; serialize dependent
decisions and shared writes. Author `depends_on` only where one claim logically
requires another:

```json
{"id":"P2","claim":"An authorized invitation persists and survives reload.",
 "verification":"Exercise the invitation through the public API and reopen it.",
 "depends_on":["P1"]}
```

The dependency graph must contain known unique IDs and no cycles. An omitted or
empty dependency list preserves the existing flat contract. A dependent pass is
refused unless every ancestor passes with valid supporting evidence. A changed
prerequisite status or supporting run list conservatively demotes transitive passed
descendants to `partial`, retaining their old references and an explanation. Details
or artifact-only edits do not trigger this demotion; meaningful claim changes still
require new proof even when the CLI cannot infer their significance.

After defining the contract, fill the report's narrative fields with honest current
judgments. Use `not_run` and explicit gaps rather than leaving malformed templates.
The planner accepts valid unfinished reports, including failed simplicity gates.

## Choose the next useful action

```sh
python3 "$CP" next --directory .confidence --json
```

This command validates the evidence before listing `ready` obligation IDs and
`blocked` obligations with incomplete direct prerequisites. It also returns
`completion_errors` and recorded `source_scopes`. It never executes verification
text, starts a model, writes evidence, or emits telemetry. Repeated reads of stable
inputs produce the same JSON. Invalid or stale proof, or tampering that breaks
retained integrity checks, returns `ok:false`,
an empty frontier and exit 1; repair the stated evidence problem first. `ok:true`
means the documents are valid, not that the task is finished. `complete:true` means
the mechanical completion gates pass, not that every product claim is true.

Prefer the ready action that resolves the greatest consequential uncertainty. Test
the actual failure before fixing it; keep that diagnostic run. Do not multiply
passing checks that attack the same claim. When a check fails, inspect its output,
change one relevant hypothesis, and rerun the affected proof. Repeated attempts with
the same failure and no new evidence should trigger a different approach or a
precise blocker, not unlimited retries. Preserve useful partial results and finish
authorized independent work before asking for missing external input.

Record attempted checks separately from completed captures. After interrupted or
ambiguous external actions, inspect durable state and receipts before retrying;
retry only a reconciled action under its actual idempotency contract. Reserve room
to persist evidence and report an unfinished result even when the work budget ends.

## Make review attributable

For consequential complex work opt into the stronger gate in the contract:

```json
"review_policy":{"records_required":true,"implementer":"main-agent",
 "required_roles":["test_designer","adversarial_reviewer"]}
```

`required_roles` pins roles in the contract so deleting a report role cannot drop
that requirement. Omitted pinned roles preserve the earlier opt-in behavior, with
roles declared only in the report. Removing or rewriting the policy changes the
trusted contract; this is not protected against a malicious contract author.

Set `report.review.required:true` and the required roles. Add `review.records` with
one or more records for each role. Each record names `id`, `role`, `reviewer`,
`model`, `harness`, `scope` (obligation IDs), `question`, `findings`, `independent`
(a boolean declaration), and `status`. A passing record additionally needs:

- `reference`: a regular artifact inside the evidence directory, preferably
  `runs/<review-id>.log`, containing the actual captured review output.
- `reference_sha256`: the SHA-256 of that artifact, not a generated summary alone.
- `run_id`: a successful captured review command with an intact log.
- `contract_sha256`: `contract_digest(contract)` from `confidence.py`, SHA-256 of
  UTF-8 JSON with sorted keys, compact separators, and ASCII escaping. This binds
  review to the whole current contract; formatting alone does not change it.

Arbitrary review files in an unignored evidence directory are source inputs, unlike
the reserved untracked capture outputs. Finalize such artifacts before capture or
use an intentionally ignored task evidence directory. Do not broaden generated-file
exclusions to hide source. Referencing the captured review log avoids an extra
publication that could stale earlier proof.

Pass records from independent reviewers other than the named implementer must
together cover every obligation for each required role. Critical work requires
different reviewer identities for proof design and adversarial review. Identity
comparison trims whitespace and ignores case. Missing records, deleting records,
unresolved record statuses, changed artifacts, changed intent, failed captures and
stale code reviews cannot satisfy completion. For corrected findings, preserve the
original artifact in history and supply a fresh passing review of the final state;
do not relabel unresolved findings to force the gate.

Test design happens before implementation, so its capture may reference historical
source. Its artifact integrity, successful capture and current contract digest are
still checked. Other passing review roles require current source binding for
software work. References and captures retain their recorded source locations;
passing software reviews must also share the source root of their scoped supporting
proof. A current review from an unrelated repository cannot cover those obligations.
copying a report never certifies a different checkout. See [evidence](evidence.md)
for excluded inputs and observation limits.

These records check **declared** provenance and evidence consistency. They cannot
authenticate a person's identity, verify that a reviewer read the diff, prevent
collusion, or prove semantic independence. A writer controlling all records can
forge hashes. Legacy contracts without this opt-in keep their previous gates;
legacy role names do not become attributable evidence automatically.

## Resume without losing intent

After compaction, a harness switch, a fresh agent, or interruption, reread the
contract and report. Preserve IDs, authority already granted, unresolved choices,
required checks and review origins. Inspect existing run receipts and reconcile
ambiguous attempts. Recompute `next` against current evidence instead of trusting a
handoff summary's pass labels. Recover interrupted contract-only initialization
with `init --resume`; do not overwrite authored evidence to make progress look clean.
Use the same task evidence directory across cooperating agents, or explicitly
reconcile separate scopes. Shared authors must use the locking CLI rather than
concurrent manual report edits. Finish with `validate --require-complete` and the
rendered report, or a truthful partial outcome and the smallest remaining blocker.
