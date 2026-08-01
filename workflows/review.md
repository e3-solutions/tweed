# Tweed Implementation Review

Independently review the current implementation against an approved `Status: scoped` report, apply only evidence-backed in-scope corrections, and repeat until the complete implementation has zero unresolved material findings. The runner normally supplies a Linear issue identifier; use Linear MCP read tools to retrieve its completed RCA, scope, and implementation handoff. Do not redesign or broaden the approved solution.

## Rules

- Treat the supplied scope, repository snapshot, non-goals, acceptance criteria, and validation as the contract. Use the completed implementation report only for baseline and ownership provenance; do not trust its quality claims.
- Permit local repository fixes, validation, and reading the supplied Linear issue only. Preserve the Git index exactly; do not stage or unstage. Do not commit, branch, stash, reset, clean, push, open a PR, update Linear during review, deploy, publish, mutate remote services or data, or run an irreversible migration.
- Preserve pre-existing user work and unrelated dirty paths. Never overwrite, revert, or attribute them to the review.
- Reviewers never edit. Only a separately assigned fixer may change a validated finding's owned surface.
- Agent agreement does not make a finding material; evidence does. Do not require an agent to invent a finding.
- Research exact-version language, framework, and installed-library capabilities from repository metadata and primary sources before accepting custom code that appears to duplicate them.

## Preflight

Before writing, verify the repository path and `HEAD` match the scope snapshot. Verify the implementation handoff's scope digest, baseline HEAD/ref, complete pre-existing dirty/index manifest, and implementation-owned `baseline → final` path manifest against the supplied scope and current workspace. Require the current staged, unstaged, and untracked path set to equal the disjoint union of the pre-existing manifest and implementation-owned manifest; any unaccounted or multiply owned path blocks automatic fixes. Derive the review target from the owned paths. Do not require implementation-owned targets to match scope-baseline hashes because they contain the implementation under review; require their current hashes to match the handoff's final hashes.

Record a fingerprint of the entire current workspace and index. Return `Status: blocked` before edits when either handoff is missing or ambiguous, `HEAD` moved, a pre-existing user path or index entry changed, an implementation-owned path no longer matches its handoff, implementation changes cannot be distinguished safely from user work, or the review target cannot be resolved inside the approved change surface. Without exact provenance, review may report read-only observations but must not apply fixes.

## Review workflow

1. Start independent non-writing reviewers on five axes:
   - **Simplicity, clarity, reuse, and scope fidelity:** Aggressively seek deletion and reduction. Find unnecessary hunks, nesting, abstractions, dependencies, duplication, compatibility shims, cleanup, and custom code already covered by a project utility, language or framework built-in, or installed library. Verify exact-version behavior from repository evidence, official documentation, or source. Require every diff hunk to serve an approved step or acceptance criterion and every non-goal to remain excluded.
   - **Correctness and robustness:** Trace the changed behavior and realistic failure paths, including state transitions, validation, error handling, partial failure, data integrity, and concurrency when applicable.
   - **Compatibility and integration:** Trace changed interfaces to their callers and consumers. Check public APIs, wire and storage formats, CLI/config/environment behavior, supported runtime or dependency versions, forward and backward compatibility, mixed-version operation, upgrade ordering, rollback or downgrade behavior when applicable, and existing contract or integration tests.
   - **Performance and resource use:** Examine relevant hot paths, algorithmic work, allocations, queries, I/O, caching, batching, and concurrency overhead. Prefer existing performant primitives and require measurement, execution-path evidence, or a concrete scaling argument for material findings.
   - **Verification quality:** Map every acceptance criterion to implementation and a proving check. Challenge missing regressions, assertions that do not prove behavior, untested failure paths, and unexplained build/type/lint/test failures.
2. Add a performance, security or privacy, accessibility, data, concurrency, migration, operations, or other specialist only when a concrete changed boundary creates a material question.
3. Require every proposed finding to include a stable ID, axis, material consequence, violated scope item, acceptance criterion, non-goal, or verified contract, file:line or runtime evidence, owning surface, minimum correction, and proving check.
4. The coordinator reproduces or traces findings, deduplicates them, and records each as accepted or rejected with evidence before any fix. Reject style preferences, equivalent rewrites, hypothetical hardening, generic future-proofing, unrelated pre-existing defects, subjective readability refactors, unsupported performance concerns, and tests that do not prove scoped behavior.
5. Assign each accepted finding to exactly one bounded fixer. Run fixes concurrently only when complete write and command-side-effect surfaces are disjoint; serialize overlaps and shared mutable outputs. A fixer receives the finding, approved boundary, non-goals, acceptance criteria, and proving check. It cannot close its own finding.
6. After every fix, the coordinator inspects the diff and reruns the finding's proving check. A non-authoring reviewer re-reviews the affected surface. Rerun compatibility review whenever a boundary or contract changes, and rerun every affected acceptance check after a simplicity correction.
7. Continue only while an evidence-backed material finding has a bounded in-scope correction or a new concrete diagnostic can add evidence or adjudicate a conflict. If findings repeat without new evidence, fixes oscillate, or reviewers conflict, stop only when no further bounded in-scope diagnostic or correction can make progress.
8. When targeted findings clear, run a fresh whole-diff pass across all five baseline axes and every triggered specialist. Then run exact acceptance checks and the relevant broader build, type, lint, contract, integration, and test suites. Convert a material clean-pass finding or relevant final-check failure into the same evidence-backed finding format, return it to the bounded fix and targeted re-review loop, and repeat the whole-diff clean pass after correction.

For a behavior or regression finding, add a regression check when feasible. Never trust a fixer's reported pass without rerunning the check.

## Fix boundary

Apply the minimum correction only when it stays inside an approved path and behavior, introduces no new public interface, dependency, schema, migration, configuration, rollout, or product choice, and does not change a non-goal or acceptance criterion. Prefer removing an unnecessary hunk over rewriting valid code.

If a finding proves the approved design or step is wrong or incomplete, needs a new component or path, changes observable behavior, or requires a new dependency, interface, schema, migration, rollout contract, product decision, or architecture choice, do not fix it here. Return it to scoping with the exact evidence and decision needed.

## Status semantics

- `reviewed`: The final whole-diff pass has zero unresolved validated material findings and every relevant check passes. In-scope fixes may have been applied.
- `blocked`: Review cannot complete and no review edit was made, whether because preflight is unsafe or stale, resolution requires re-scoping, or a reviewer, diagnostic, or check failed before correction.
- `partial`: Review edits exist, but a finding, failed check, interruption, oscillation, conflict, or scope-crossing correction prevents completion. Preserve and report the actual changes; do not roll them back automatically.

## Completion gate

Return `Status: reviewed` only when:

- every final diff hunk maps to an approved step or acceptance criterion;
- every acceptance criterion has passing evidence;
- no unnecessary machinery, duplication, dependency, or unrelated cleanup remains;
- no custom code remains where a verified built-in, project utility, or installed library provides a simpler equivalent without a material tradeoff;
- relevant hot paths have no evidence-backed avoidable performance or resource regression;
- realistic failures at changed boundaries are handled;
- compatibility is established for every changed interface and consumer, including mixed-version, rollback, and downgrade behavior when applicable;
- non-goals and pre-existing user work remain untouched;
- relevant broader checks pass without unexplained failure; and
- the final independent whole-diff pass has zero unresolved validated material findings.

## Output

```markdown
Status: [reviewed | blocked | partial]

# Implementation review

[Verdict and concise explanation.]

## Final axis results

- Simplicity and scope fidelity: [clean, or unresolved finding]
- Correctness and robustness: [clean, or unresolved finding]
- Compatibility and integration: [clean, or unresolved finding]
- Verification quality: [clean, or unresolved finding]
- Performance and resource use: [clean, or unresolved finding]

## Findings

| ID | Axis | Evidence | Disposition | Fixer | Re-review | Result |
|---|---|---|---|---|---|---|
| [ID] | [axis] | [file:line or diagnostic] | [accepted/rejected] | [agent or none] | [check/reviewer] | [resolved/unresolved] |

## Changes made

- [File or component]: [minimum correction and finding ID]

## Verification

- `[exact command or diagnostic]` → [result and criterion/finding proved]

## Remaining findings

["None." or the exact issue that remains.]

## Refactoring opportunities

- [Applied deletion, simplification, reuse, readability, or performance correction and its evidence]
- [Deferred tip that would require re-scope, or "None"]

## Return to scope

["None." or the evidence-backed scope change or decision required.]

## Repository state

- Review baseline: [HEAD and workspace fingerprint]
- Final: [HEAD and workspace fingerprint]
- Scope digest: [digest of the supplied report]

## Cycle summary

Approved scope and implementation diff
├─ Initial review — [accepted/rejected finding summary]
├─ Fix and targeted re-review — [resolved finding summary]
├─ Final clean pass — [zero findings or remaining issue]
└─ Result — [reviewed/blocked/partial]: [why the gate passed or failed]

## Agent map

- [Agent role/name] — [reviewed/fixed/challenged; cumulative one-line result]
```

Include every reviewer, specialist, fixer, and final-pass agent actually used exactly once in the agent map, even when it participated in multiple cycles. Do not include transcripts or tool logs.

## Linear sync

Do not use Linear write tools during review, repair, re-review, or final validation. After a `reviewed` report, the runner may send a separate message beginning exactly with `TWEED_LINEAR_SYNC`. Only on that later turn may you update the supplied issue through the configured Linear MCP, and only as requested. Never write partial findings, agent activity, or failed review cycles to Linear.
