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
  repository at that exact reviewed head. Return it without duplicating the
  phase only when every check passes; otherwise return `blocked` and name the
  missing or stale fact. Otherwise require the supplied implementation handoff,
  then extract the recorded branch, commit, and draft PR.
- Treat its carried-forward outcome, non-goals, acceptance criteria, risks, and
  validation as the contract. Treat implementation claims as provenance, not
  as proof of quality.
- For a new review, require the implementation handoff's draft PR URL. Derive
  the canonical repository from `origin`, scope every `gh` read explicitly to
  it, and verify the PR is open and draft with the recorded official branch,
  expected base, and implementation commit. A missing, duplicate, closed,
  merged, non-draft, or mismatched PR blocks review before any correction.
- Switch to the recorded branch only from a clean worktree. Require its history
  and remote PR head to contain the implementation commit. Never reset, clean,
  stash, discard, or overwrite user changes. The only GitHub write allowed is an
  ordinary non-force push of a verified review correction commit to that branch.
- Reviewers never edit. Only a separately assigned fixer may change a validated
  finding's bounded surface, and that fixer cannot close its own finding.
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
applied.

## Review workflow

1. Spawn fresh, independent, non-writing reviewers without inherited
   conversation. Run them concurrently when possible or in blind waves across:
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
2. Add a security/privacy, accessibility, data, migration, operations, or other
   specialist only when a concrete changed boundary creates a material question.
3. Require every proposed finding to include a stable ID, axis, material
   consequence, violated contract, file:line or runtime evidence, owning
   surface, minimum correction, and proving check.
4. Reproduce or trace each finding. Accept or reject it with evidence before any
   edit. Reject style preferences, equivalent rewrites, hypothetical hardening,
   generic future-proofing, unrelated defects, subjective refactors, and
   unsupported performance concerns.
5. Assign every accepted finding to exactly one bounded fixer. Serialize
   overlapping file or command effects. Inspect each fix and rerun its proving
   check; then use a non-authoring reviewer to recheck the affected surface.
6. If a finding proves the approved design is incomplete or requires a new
   component, behavior, dependency, interface, schema, migration, rollout, or
   product decision, do not fix it in review. Return `blocked` with the exact
   evidence and change that must go back to scope.
7. When targeted findings clear, run a fresh whole-diff pass across all baseline
   axes, followed by the exact acceptance checks and relevant broader build,
   type, lint, contract, integration, and test suites. A new material finding
   re-enters the bounded fix and re-review loop.
8. If fixes were made, stage only review-owned changes and create one additional
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
- no unnecessary machinery, duplication, dependency, or unrelated cleanup
  remains;
- realistic failures at changed boundaries are handled;
- compatibility is established for each changed interface and consumer;
- relevant hot paths have no evidence-backed avoidable regression;
- non-goals and user work remain untouched;
- relevant broader checks pass without unexplained failure;
- a fresh independent whole-diff pass has zero unresolved material findings;
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

### Verification
| Exact command or diagnostic | Result | Contract/finding proved | Coverage boundary |
|---|---|---|---|
| `[command]` | [pass/fail and salient counts] | [criterion/finding] | [files/interface] |

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
