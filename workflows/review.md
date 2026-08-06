# Tweed Implementation Review

Independently review the implementation recorded in the supplied Linear issue
against its approved Tweed scope. Use Linear MCP yourself to read the issue and
Tweed comments, check for an existing review, and publish the final review.
Children must not use Linear. Apply only evidence-backed, in-scope corrections
and stop at a clean reviewed local commit. Preserve the implementation draft PR
without pushing, changing its metadata or readiness, merging, deploying, or
performing other remote delivery actions.

## Contract and safety

- Require solution scope and implementation comments. A bug also requires an
  established RCA; a feature does not. Extract the recorded branch and commit.
  If a review comment already exists, verify its branch and commit locally and
  return it without duplicating the phase.
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

### Final axis results
- Simplicity and scope fidelity: [clean]
- Correctness and robustness: [clean]
- Compatibility and integration: [clean]
- Performance and resource use: [clean]
- Verification quality: [clean]

### Findings
| ID | Axis | Evidence | Disposition | Fix | Re-review |
|---|---|---|---|---|---|
| [ID or None] | [axis] | [evidence] | [accepted/rejected] | [result] | [result] |

### Changes made
- [Finding ID and minimum correction, or “None.”]

### Verification
- `[exact command]` → [result and contract proved]

### Remaining findings
None.

### Git handoff
- Branch: `[branch]`
- Implementation commit: `[commit]`
- Reviewed commit: `[full final commit]`
- Draft PR: `[URL from the implementation handoff, or “None” for a legacy
  handoff]`
- Worktree: clean

### Review map
- [Reviewer/fixer role] — [reviewed/fixed/challenged]: [one-line result]
- Final clean pass — reviewed: zero unresolved material findings
```

Include every reviewer, specialist, and fixer once. Do not include transcripts,
tool logs, hashes, or unscoped tips.

## Receipt

Return only the runner-provided JSON receipt with `phase: review`. Success uses
`state: completed`, `result: reviewed`, the issue identifier and URL, and the
exact branch and final commit, plus the unchanged draft PR URL when present.
Clarification uses `needs-input`. All other incomplete outcomes use
`state: blocked`, with `result: blocked` or `partial` and the safest next action.
