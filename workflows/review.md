# Bonaparte Implementation Review

Independently review the supplied latest implementation handoff. It carries the
approved outcome, acceptance criteria, non-goals, risks, implementation, and
verification needed by this phase. The runner supplies only that implementation
or an existing review result, plus issue metadata. Use Linear only to publish
and verify the final review. Children must not use Linear. Apply only
evidence-backed, in-contract corrections and stop at a clean reviewed local
commit. Push verified correction commits to the implementation draft PR, but do
not create another PR, change its metadata or readiness, merge, or deploy.

## Contract and safety

- If an `existing` review was supplied, validate it under the current gate and
  comment schema, then verify its branch, commit, and recorded PR. The PR may be
  draft or already published, but it must remain open in the canonical
  repository at that exact reviewed head. Return a current-schema review without
  duplicating the phase only when every check passes; a stale current-schema
  review returns `blocked` with the missing fact. The immediately preceding
  legacy schema is handled by the next rule. Without an `existing` review,
  require the supplied implementation handoff and extract its recorded branch,
  commit, and draft PR.
- Treat an `existing` review as the immediately preceding legacy schema only
  when it contains its review basis, final axis results, findings, changes,
  `### Verification`, remaining concerns, Git handoff, and review map, but lacks
  `### Evidence ledger`. For that case only, rebuild the ledger from its carried
  acceptance criteria and changed boundaries at the exact recorded head, run
  the current independent verification workflow, and publish one refreshed
  current-schema review comment when the completion gate passes. Legacy checks
  are evidence candidates, not inherited `pass` results. The missing ledger
  alone is not a blocker; any missing contract or provenance fact, failed or
  unverified obligation, or required unsafe correction follows the normal
  blocked or finding rules.
- Treat its carried-forward outcome, non-goals, acceptance criteria, risks, and
  validation as the contract. Treat implementation claims as provenance, not
  as proof of quality.
- Implementation-author tests and diagnostics remain provisional. Green tests
  introduced by the patch do not alone prove an external or native contract.
- For a new review, require the implementation handoff's draft PR URL. Derive
  the canonical repository from `origin`, scope every `gh` read explicitly to
  it, and verify the PR is open and draft with the recorded official branch,
  expected base (from trusted supplemental input when present), and implementation
  commit. A missing, duplicate, closed, merged, non-draft, or mismatched PR
  blocks review before any correction.
- Switch to the recorded branch only from a clean worktree. Require its history
  and remote PR head to contain the implementation commit. Never reset, clean,
  stash, discard, or overwrite user changes. The only GitHub write allowed is an
  ordinary non-force push of a verified review correction commit to that branch.
- Reviewers never edit. The coordinator or one separately assigned worker may
  change a validated finding's bounded surface; an author cannot adjudicate a
  judgment-dependent recheck of its own correction.
- Agent agreement does not make a finding material; reproducible evidence does.
- Research exact installed versions and primary sources before claiming custom
  code duplicates an existing library or framework capability.

## Preflight

Record the repository, branch, current `HEAD`, implementation commit, draft PR,
and Git status. A clean reviewed commit may be newer than the implementation
commit, but the implementation commit must remain in its ancestry. Before
automatic fixes, require a clean worktree on the issue branch. A new review
requires the draft at the recorded implementation head; an existing review may
observe the same open PR at its recorded reviewed head and later published
readiness. If state is ambiguous or user work could be overwritten, return
`blocked`; read-only observations may be reported in the receipt but must not be
applied. Give every pass one canonical range—verified base merge-base through the
recorded head—and changed-path inventory; recompute both after corrections.

## Review workflow

1. Rebuild the evidence ledger at the exact review target. The coordinator may
   verify simple local logic. For every changed external/native protocol,
   process lifecycle, persistence/concurrency, or producer-consumer boundary,
   assign a fresh read-only verifier within the zero-to-three reviewer total in
   step 2. One verifier may cover all compatible obligations; add another only
   when evidence or tool boundaries are incompatible. Give it the contract,
   canonical range, changed paths, affected consumers, and required evidence—not
   the author's conclusions. It must inspect the implementation and run the
   smallest decisive checks. Record each obligation as `pass`, `fail`, or
   `unverified`; tracing cannot close a boundary requiring runtime evidence.
2. The coordinator owns the baseline whole-diff review and combines applicable
   axes for a narrow diff. Add zero to three non-writing reviewers only for
   separable questions that can change the verdict:
   - **Simplicity, clarity, reuse, and scope fidelity:** seek deletion and
     reduction; challenge unnecessary hunks, nesting, abstractions,
     dependencies, duplication, compatibility shims, cleanup, and custom code
     already covered by verified project or installed capabilities.
   - **Correctness and robustness:** trace changed behavior and realistic
     failures, including state transitions, validation, error handling, partial
     failure, data integrity, and concurrency when applicable.
   - **Compatibility and integration:** trace interfaces to callers and
     consumers; check APIs, formats, CLI/config behavior, supported versions,
     mixed-version behavior, and rollback constraints when applicable.
   - **Performance and resource use:** inspect relevant algorithms,
     allocations, queries, I/O, caching, batching, and concurrency overhead;
     require measurement or a concrete execution-path argument.
   - **Verification quality:** map every acceptance criterion to implementation
     and a proving check; challenge missing regressions, weak assertions,
     untested failures, and unexplained check failures.
3. Give each reviewer the canonical range and affected consumers. Require actual
   code and repository evidence, not implementation summaries. Add a specialist
   only for a concrete changed-boundary risk.
4. Require every proposed finding to include a stable ID, axis, material
   consequence, violated contract, file:line or runtime evidence, owning
   surface, minimum correction, and proving check.
5. Reproduce or trace each finding. Accept or reject it with evidence before any
   edit. Reject style preferences, equivalent rewrites, hypothetical hardening,
   generic future-proofing, unrelated defects, subjective refactors, and
   unsupported performance concerns.
6. Assign every accepted finding to exactly one bounded fixer. Serialize
   overlapping file or command effects. Inspect each fix and rerun its proving
   check. Use a non-authoring reviewer for a judgment-dependent recheck; a
   deterministic proving check is sufficient for a mechanical correction.
7. If a finding proves the approved design is incomplete or requires a new
   component, behavior, dependency, interface, schema, migration, rollout, or
   product decision, do not fix it in review. Return `blocked` with the exact
   evidence and change that must go back to scope.
8. If a correction changes a proof-obligation boundary, its non-authoring
   verifier must rerun that obligation. If any correction changes the diff,
   repeat the whole-diff review across all
   applicable axes; otherwise the baseline review is final. Then run the exact
   acceptance checks and only the broader build, type, lint, contract,
   integration, and test suites justified by the affected surface. A new
   material finding re-enters the bounded fix and re-review loop.
9. If fixes were made, stage only review-owned changes and create one additional
   commit containing the issue ID. Never rewrite the implementation commit.
   Rerun the proving checks, push the correction normally to the same draft PR,
   and verify its head is the final reviewed commit. If no fix was needed, verify
   the draft still points at the implementation commit. Require a clean worktree.

Continue only while a bounded correction or concrete diagnostic can resolve a
material finding. Stop if fixes oscillate or evidence cannot adjudicate a
conflict. Never require an agent to invent a finding.

## Completion gate

Call the phase reviewed only when:

- every final diff hunk maps to the carried-forward contract or an accepted
  correction;
- every acceptance criterion has passing evidence;
- the final evidence ledger contains only `pass`; no criterion is failed or
  unverified, and every independence-required obligation has direct evidence
  from its designated verifier;
- no unnecessary machinery, duplication, dependency, or unrelated cleanup
  remains;
- realistic failures at changed boundaries are handled;
- compatibility is established for each changed interface and consumer;
- relevant hot paths have no evidence-backed avoidable regression;
- non-goals and user work remain untouched;
- relevant broader checks pass without unexplained failure;
- the final whole-diff review has zero unresolved material findings;
- the worktree is clean and the verified PR points at the final reviewed commit.
  It is draft for a new review; an idempotent retry may observe later published
  readiness only when the existing review records the same PR and commit.

If no review edit was made and review cannot complete, return `blocked`. If
review edits exist but a finding, failed check, interruption, or contract-crossing
correction prevents a passing commit, preserve the changes and return `blocked`
with `result: partial`. Do not publish a Linear review comment until the gate
passes. If a correction commit was pushed before a later block, preserve it and
report the draft URL and current head so a retry can resume safely.

## Linear comment

After the reviewed commit exists, publish exactly one:

After writing, re-read the comment and return `completed` only if it matches
this schema and contains the evidence required by the completion gate.

```markdown
## Bonaparte · Implementation Review

**Verdict:** Ready to publish

### Review basis
- Contract carried forward: [outcome, acceptance criteria, non-goals, and risks from the implementation handoff]
- Implementation reviewed: [branch and full implementation commit]
- Review target: [changed files, boundaries, interfaces, and consumers]

### Final axis results
| Axis | Result | Evidence | Remaining concern |
|---|---|---|---|
| Simplicity and scope fidelity | [clean/finding] | [diff/repository evidence] | [None or concern] |
| Correctness and robustness | [clean/finding] | [runtime/test evidence] | [None or concern] |
| Compatibility and integration | [clean/finding] | [caller/consumer evidence] | [None or concern] |
| Performance and resource use | [clean/finding] | [path/measurement evidence] | [None or concern] |
| Verification quality | [clean/finding] | [criterion/check mapping] | [None or concern] |

### Findings
| ID | Axis | Material consequence/contract | Evidence | Disposition | Fix | Re-review |
|---|---|---|---|---|---|---|
| [ID or None] | [axis] | [consequence and violated contract] | [`file:line` or diagnostic] | [accepted/rejected and why] | [commit/file result or None] | [independent proof] |

### Changes made
- [Finding ID and minimum correction, or “None.”]

### Evidence ledger
| Acceptance criterion | Boundary and proof obligation | Owner | Exact command or diagnostic | Status | Observed evidence |
|---|---|---|---|---|---|
| [criterion] | [boundary and required proof] | [coordinator/verifier] | `[check]` | [pass/fail/unverified] | [observed result] |

### Remaining concerns
[Non-blocking operational or CI caveat, or “None.”]

### Git handoff
- Branch: `[branch]`
- Implementation commit: `[commit]`
- Reviewed commit: `[full final commit]`
- Draft PR: `[URL]`
- Worktree: clean

### Review map
| Role | Material conclusion | Evidence | Affected surface | Confidence | Relationship |
|---|---|---|---|---|---|
| [Reviewer/fixer role] | [substantive finding or fix result] | [`file:line` or diagnostic] | [files/boundary] | [high/medium/low and why] | [reviewed/fixed/challenged] |

**Final clean pass:** [Evidence-backed result across the whole diff and why
zero unresolved material findings remain.]
```

Include every reviewer, specialist, and fixer once. Do not include transcripts,
tool logs, hashes, or unscoped tips.

## Receipt

Return only the runner-provided JSON receipt with `phase: review`. Success uses
`state: completed`, `result: reviewed`, the issue identifier and URL, and the
exact branch, final commit, and unchanged draft PR URL. Clarification uses
`needs-input`. All other incomplete outcomes use `state: blocked`, with
`result: blocked` or `partial` and the safest next action.
