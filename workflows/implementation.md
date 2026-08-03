# Tweed Implementation

Implement the approved scope from the supplied frozen Linear issue snapshot using bounded Codex subagents. Modify only the runner-owned integration worktree and stop after verified implementation. Do not redesign the solution or perform external delivery actions.

## Rules

- Treat the supplied scope, non-goals, acceptance criteria, implementation steps, and repository snapshot as the approved contract.
- Honor the scope's reuse research. Prefer existing project utilities, language or framework built-ins, and installed dependencies over new custom code when their verified behavior satisfies the contract.
- Verify the issue is at stage `ready-to-implement`; otherwise return `blocked` before editing.
- Permit repository edits and local validation only. Preserve the Git index exactly; do not stage or unstage. Do not commit, branch, stash, reset, clean, push, open a PR, use Linear tools, deploy, publish, mutate remote services or data, or run an irreversible migration. The runner owns the branch and final commit.
- Preserve pre-existing user changes. Never overwrite, revert, or attribute them to this run.
- Add dependencies, lockfile changes, schemas, migrations, public interfaces, generated assets, or configuration only when the approved scope explicitly requires them.
- Do not broaden behavior, perform unrelated cleanup, or invent a missing product or architecture decision.

## Workflow

1. **Preflight without writing.** Parse the approved scope and record its digest, repository path, `HEAD`, relevant dirty state, per-file `path → SHA-256 | ABSENT` evidence snapshot, change surface, implementation steps, non-goals, acceptance criteria, and validation. Confirm the current repository identity, planned targets, material interfaces and tests, and evidence hashes still match; every `ABSENT` target must still be absent. Snapshot the complete staged, unstaged, and untracked path manifest with worktree and index hashes, plus content hashes for intended write paths. Allow unrelated dirty files, but return `Status: blocked` if a planned path is already dirty, the write surface cannot be resolved safely, the plan is materially stale, or any approved step or acceptance criterion requires a prohibited external action. Name the delivery step that must be separated or re-scoped.
2. **Build the work graph.** Translate the approved steps into dependency-aware work packets. Group cohesive work on one boundary; split work only when ownership or verification differs. Each packet must contain its allowed surface, required behavior, dependencies, reuse decision, non-goals, acceptance criteria, and proving checks.
3. **Assign writers.** Give each file or path exactly one writer. Treat every command's generated files, caches, lockfiles, fixtures, and other side effects as part of its write surface. Run ready packets concurrently only when their complete write surfaces and integration points are disjoint; serialize overlapping or dependent work. Always serialize global formatters, package managers, code generation, migrations, and validations with shared mutable outputs unless isolation is proven. Before editing, every writer must re-read its files and verify owned-path hashes still match its assigned baseline.
4. **Require concise returns.** Every writer reports only its completed scope items, files changed, checks run and results, blocker, and deviation. It may make a narrow clarification only inside the approved boundary when necessary for an existing acceptance criterion and when it adds no behavior, interface, dependency, or migration. Record that clarification.
5. **Reconcile every wave.** The coordinator inspects the actual diff against the baseline, maps each hunk to an approved step, reruns the packet's proving checks when feasible, and only then unlocks dependents. If an agent fails or unexpected drift appears, stop launching writers and inspect the actual workspace before reassigning; never assume a failed agent made no changes.
6. **Review independently.** After integration, use independent subagents that authored no code on three baseline axes:
   - **Simplicity, clarity, reuse, and performance:** Aggressively look for code to delete, flatten, or replace with verified project utilities, built-ins, or already-installed libraries. Challenge duplication, needless abstraction, allocations, queries, I/O, and hot-path overhead. Require exact-version evidence and behavior-preserving checks; do not accept subjective rewrites.
   - **Correctness, robustness, and verification:** Falsify changed behavior and failure paths, map acceptance criteria to evidence, and challenge tests that do not prove the contract.
   - **Compatibility and integration:** Trace changed interfaces to callers and consumers and check formats, configuration, supported versions, mixed-version behavior, and rollback constraints when applicable.
   Add a security, data, concurrency, migration, accessibility, operations, or other specialist only for a concrete material risk.
7. **Resolve findings.** Route each evidence-backed finding to the owning writer as a bounded follow-up. Re-review only affected surfaces. Continue while a concrete fix or check can resolve a material finding; do not add arbitrary agents or rounds.
8. **Validate and report.** Run the smallest checks proving each acceptance criterion, then the relevant broader build, type, lint, and test checks supported by the project. Reinspect the final diff and repository state before applying the completion gate.

If implementation exposes a required product decision, new component or interface, dependency, schema, migration, rollout need, or contradiction in the approved design, do not rescope it here. Stop affected work and identify the exact change that must return to the scoping phase.

## Status semantics

- `implemented`: Every gate passes.
- `blocked`: Implementation cannot complete and no implementation edit was made, whether because preflight is unsafe or stale, a decision is missing, or a writer, diagnostic, or check failed before mutation.
- `partial`: Implementation edits exist, but a blocker, failed check, interruption, material deviation, or unresolved finding prevents completion. Preserve and report the actual changes; do not roll them back automatically.

## Completion gate

Return `Status: implemented` only when:

- every approved scope item and acceptance criterion maps to the final diff and passing evidence;
- every approved implementation step is complete; discovering an unnecessary step is a scope contradiction that must return to scoping;
- every diff hunk is explained by the scope, with non-goals and unrelated user changes untouched;
- the Git index and every pre-existing staged, unstaged, or untracked path remain unchanged;
- relevant build, type, lint, test, and behavior checks pass without an unexplained failure;
- realistic failure and compatibility behavior at changed boundaries is covered;
- no unnecessary custom code, abstraction, duplication, or evidenced performance regression remains when a simpler verified built-in, project utility, or installed-library path exists;
- no unauthorized dependency, interface, migration, cleanup, or external side effect occurred; and
- an independent verifier has no material unresolved finding.

For a bug fix, include a regression check that reproduces the original failure when feasible. If any gate fails, return `Status: blocked` when no implementation edit exists and `Status: partial` otherwise.

## Output

```markdown
Status: [implemented | blocked | partial]

# Implementation

[What was delivered, or why work stopped.]

## Delivered

- [Scope item or acceptance criterion] → [files]

## Changes

- [File or component]: [concise responsibility changed]

## Verification

- `[exact command or diagnostic]` → [result and acceptance criterion proved]

## Review findings

- [Finding] → [fixed/rejected/unresolved] because [evidence]

## Deviations

[Recorded narrow clarifications, or "None."]

## Refactoring opportunities

- [Applied in-scope simplification, deletion, reuse, or performance correction and its evidence]
- [Deferred tip requiring re-scope, or "None"]

## Remaining work

[Nothing, or exact blocked/partial work that must return to scope or implementation.]

## Repository state

- Baseline: [HEAD and relevant dirty state]
- Final: [HEAD and relevant dirty state]
- Scope digest: [digest of the supplied report]

## Review handoff

- Scope digest: [SHA-256 of the complete supplied scope]
- Baseline HEAD/ref: [commit and symbolic ref]
- Pre-existing workspace/index manifest:
  - [path] | [staged/unstaged/untracked status] | worktree [SHA-256/ABSENT] | index [SHA-256/ABSENT]
- Implementation-owned paths:
  - [path] | baseline [SHA-256/ABSENT] | final [SHA-256/ABSENT]

## Implementation map

Approved scope
├─ [Agent role] — [authored/reviewed/challenged]: [one-line result]
├─ [Agent role] — [authored/reviewed/challenged]: [one-line result]
└─ Synthesis — [implemented/blocked/partial]: [why the gate passed or failed]
```

Include every agent actually used once in the map. Do not include transcripts or tool logs.

## Structured return

Return the result through the runner-provided JSON schema with `status`, a bounded `summary`, optional structured `question`, and the complete report in `report_markdown`. The report must begin with the matching `Status:` line. Never use Linear tools; the runner alone persists a completed phase and commits a passing worktree.
