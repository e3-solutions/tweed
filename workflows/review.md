# Tweed Implementation Review

Independently review the implementation recorded in the supplied Linear issue
against its approved Tweed scope. Use Linear MCP yourself to read the issue and
Tweed comments, check for an existing review, and publish the final review.
Children must not use Linear. Apply only evidence-backed, in-scope corrections
and stop at a clean reviewed local commit. Do not push, open or merge a pull
request, deploy, or perform remote delivery actions.

## Durable phase boundary

- This is a fresh phase coordinator. Its only request-specific input is the
  Linear issue identifier. Read the issue description and all completed Tweed
  comments from Linear. Do not expect or accept inherited coordinator/subagent
  context, implementation material injected into the prompt, hidden files, or
  local phase state.
- The completed Linear comments are the complete durable review input. The JSON
  receipt is control-plane data only. Resuming this same coordinator after
  `needs-input` is the sole within-phase context exception.
- Before returning `completed`, publish and re-read the review comment. It must
  let a fresh publish coordinator establish readiness, provenance, validation,
  and remaining concerns using only Linear and the repository. If any material
  finding, evidence, fix, validation result, or concern remains only in this
  coordinator's context, do not complete the phase.

## Contract and safety

- Require solution scope and implementation comments. A bug also requires an
  established RCA; a feature does not. Extract the recorded branch and commit.
  Validate every required comment against its current self-contained handoff
  schema; never reconstruct missing facts from non-Linear context. If a review
  comment already exists, return it without duplicating the phase only after
  its complete handoff and branch/commit are verified locally. Otherwise return
  `blocked` and name the missing or stale fact.
- Treat the scope, non-goals, acceptance criteria, and validation as the
  contract. Use the implementation comment as provenance, not as proof of
  quality.
- Switch to the recorded branch only from a clean worktree. Require its history
  to contain the implementation commit. Never reset, clean, stash, discard, or
  overwrite user changes.
- Reviewers never edit. Only a separately assigned fixer may change a validated
  finding's bounded surface, and that fixer cannot close its own finding.
- Agent agreement does not make a finding material; reproducible evidence does.
- Research exact installed versions and primary sources before claiming custom
  code duplicates an existing library or framework capability.

## Preflight

Record the repository, branch, current `HEAD`, implementation commit, and Git
status. A clean reviewed commit may be newer than the implementation commit, but
the implementation commit must remain in its ancestry. Before automatic fixes,
require a clean worktree on the issue branch. If state is ambiguous or user work
could be overwritten, return `blocked`; read-only observations may be reported
in the receipt but must not be applied.

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
   Consolidate every material reviewer, specialist, and fixer conclusion in the
   final review map with its evidence, affected files or boundary, objection or
   risk, confidence, and unresolved gap. Do not publish raw returns,
   transcripts, or tool logs.
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
   Require a clean worktree at the final reviewed commit.

Continue only while a bounded correction or concrete diagnostic can resolve a
material finding. Stop if fixes oscillate or evidence cannot adjudicate a
conflict. Never require an agent to invent a finding.

## Completion gate

Call the phase reviewed only when:

- every final diff hunk maps to the approved scope or an accepted correction;
- every acceptance criterion has passing evidence;
- no unnecessary machinery, duplication, dependency, or unrelated cleanup
  remains;
- realistic failures at changed boundaries are handled;
- compatibility is established for each changed interface and consumer;
- relevant hot paths have no evidence-backed avoidable regression;
- non-goals and user work remain untouched;
- relevant broader checks pass without unexplained failure; and
- a fresh independent whole-diff pass has zero unresolved material findings.

The verified Linear comment must itself carry all findings (including rejected
ones that were material enough to investigate), their evidence and disposition,
every fix and re-review, the final branch/commit, complete validation mapped to
the contract, remaining concerns, and an explicit readiness decision. Facts
present only in coordinator memory do not satisfy the gate.

If no review edit was made and review cannot complete, return `blocked`. If
review edits exist but a finding, failed check, interruption, or scope-crossing
correction prevents a passing commit, preserve the changes and return `blocked`
with `result: partial`. Do not publish a Linear review comment until the gate
passes.

## Linear comment

After the reviewed commit exists, publish exactly one:

```markdown
## Tweed · Implementation Review

**Verdict:** Ready to publish

### Review basis
- Approved contract: [scope comment and RCA when applicable]
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
[Remaining finding, operational/CI caveat, or “None.”]

### Git handoff
- Branch: `[branch]`
- Implementation commit: `[commit]`
- Reviewed commit: `[full final commit]`
- Worktree: clean

### Readiness
- Delivery state: Ready to publish
- Evidence: [why scope, findings, validation, and Git provenance support readiness]
- Conditions still outside this phase: [CI/publish/rollout conditions, or “None.”]

### Review map
| Role | Material conclusion | Evidence | Affected surface | Objection or risk | Confidence | Unresolved gap | Relationship |
|---|---|---|---|---|---|---|---|
| [Reviewer/fixer role] | [substantive finding or fix result] | [`file:line` or diagnostic] | [files/boundary] | [objection or risk] | [high/medium/low and why] | [gap or None] | [reviewed/fixed/challenged] |

**Final clean pass:** [Evidence-backed result across the whole diff and why
zero unresolved material findings remain.]
```

Include every reviewer, specialist, and fixer once. Do not include transcripts,
tool logs, hashes, or unscoped tips. Do not reduce material conclusions to
context-free labels such as “clean.”

## Receipt

Return only the runner-provided JSON receipt with `phase: review`. Success uses
`state: completed`, `result: reviewed`, the issue identifier and URL, and the
exact branch and final commit; the PR field is null. Clarification uses
`needs-input`. All other incomplete outcomes use `state: blocked`, with
`result: blocked` or `partial` and the safest next action.
