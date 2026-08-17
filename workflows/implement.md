# Bonaparte Implementation

Implement the approved Bonaparte scope from the supplied deterministic Linear
handoff, using bounded Codex subagents only when delegation has a distinct
purpose. The runner supplies only the latest scope or existing implementation
result plus issue metadata. Use Linear only to
publish and verify the final handoff. Children must not use Linear. Work only in
the supplied local repository. Create or recover one draft pull request for the
official Linear branch and push only verified implementation commits to it. Do
not mark it ready, merge, deploy, or mutate other remote services or data.

## Contract and safety

- A new implementation requires a complete `## Bonaparte · Solution Scope`; it
  is the complete implementation contract. An `existing` implementation must
  carry the complete current schema or qualify only for the bounded legacy
  upgrade in preflight. Otherwise return `blocked` before editing or publishing
  remote state.
- Treat the scope's outcome, change surface, implementation slices, acceptance
  and proof table, and guardrails as the approved contract. Do not redesign or
  broaden it during implementation.
- Writer-authored tests and implementation claims are provisional evidence;
  they cannot close an obligation that requires independent verification.
- Prefer the scope's verified project utilities, built-ins, and installed
  dependencies. Add a dependency, lockfile change, schema, migration, public
  interface, generated asset, or configuration only when explicitly required.
- Never overwrite, discard, stash, reset, clean, or attribute pre-existing user
  work to Bonaparte. Never use destructive Git commands.
- Local file edits, local validation, branch creation, staging, and committing
  are allowed. Linear may be written only after a passing final implementation
  commit exists on the verified draft PR.
- The only allowed GitHub writes are ordinary non-force pushes of the official
  issue branch and creation or update of its one draft PR. Reuse that branch and
  PR on retries. Credentials, live migrations, production checks, PR readiness,
  merging, and deployment belong to later phases.

## Preflight

1. Read the supplied handoff. If it contains an `existing` implementation,
   validate its evidence and comment schema, then verify its branch, commit, and
   recorded PR. Return it without reimplementing only when the commit exists
   locally and the PR belongs to the repository derived from `origin`, is open,
   uses the exact branch and base, and points at that commit or a later reviewed
   descendant. A PR already marked ready is valid only as later publish state.
   Treat it as the immediately preceding legacy schema only when it contains its
   review contract, delivered behavior, changed-file responsibilities, evidence
   ledger, review findings, deviations, remaining work, Git handoff, and
   implementation map, but lacks `**Status:** Implemented`. For that case only,
   rerun steps 2 and 7–9 at the exact recorded candidate and publish one compact
   current-schema handoff without reimplementing when the completion gate passes.
   Carried checks are evidence candidates, not inherited `pass` results. A
   missing contract or provenance fact, failed or unverified obligation, or
   required code change follows the normal blocked or correction rules. If only
   the PR handoff is missing, recover or create it from the verified existing
   branch and commit, then publish one refreshed implementation handoff;
   otherwise return `blocked` with the stale fact.
2. Record repository identity, current branch, `HEAD`, staged, unstaged, and
   untracked paths. Require `issue.git_branch_name` in the supplied metadata and
   validate it with `git check-ref-format --branch`. Use that exact Linear branch
   name; do not generate or substitute another branch name.
3. If the worktree is clean, create or switch to that issue branch without
   rewriting history. Reuse an existing issue branch only when its ancestry and
   contents are consistent with this issue.
4. If the expected issue branch contains uncommitted work from an interrupted
   attempt, continue only when every changed path and hunk can be mapped to the
   approved scope. Otherwise return `blocked` and preserve it exactly. Any
   unrelated dirty state blocks automatic implementation.
5. Verify that the scoped files, interfaces, dependencies, and tests still
   match current repository behavior. Return `blocked` when the scope is
   materially stale or requires an external action beyond the permitted draft
   PR workflow.
6. Require a configured GitHub `origin`, authenticated `gh`, and an identifiable
   base named by trusted supplemental input or, when absent, GitHub's default
   base. Derive one canonical `[host/]owner/repository` selector
   from `origin`; never use ambient `GH_REPO` or infer a repository from the
   working directory. Scope every `gh` read and write explicitly to that
   selector. Require the selected base to exist in the canonical remote. Require
   the issue branch to descend from it and reject unrelated commits before pushing.
7. Search all PR states for the exact head branch and inspect every match. Reuse
   exactly one only when its host, head repository, head branch, and base match
   the canonical repository and expected refs. Before implementation completes,
   it must be open and draft. A duplicate, closed, merged, cross-repository, or
   otherwise mismatched PR is ambiguous; return `blocked` without changing it.
8. If no matching PR exists, ensure the issue branch differs from the base and
   record that a draft must be created after the first meaningful, coherent,
   passing implementation commit. Do not create an empty kickoff commit or push
   merely to reserve the branch. When creating the draft, use `gh pr create
   --draft` with explicit `--repo`, `--base`, and `--head` arguments, a concise
   issue-derived title, and a body with the Linear URL, approved outcome,
   work-in-progress status, and verification. Verify its repository, refs, draft
   state, and URL before publishing the implementation handoff.

## Implementation workflow

1. Translate the approved implementation slices into dependency-aware work
   packets. Each packet must name its owned paths, required behavior and non-goals,
   dependencies, proving checks, and stop conditions for stale scope or unexpected
   state.
   Prefer the smallest complete vertical slice that leaves the repository in a
   runnable, verifiable state.
2. Create an evidence ledger from the scope's acceptance and proof table. Give each one
   an owner and record `pass`, `fail`, or `unverified`: only observed direct
   evidence is `pass`; a reproduced contradiction is `fail`; missing or
   insufficient evidence is `unverified`. Only `pass` closes an obligation.
3. The coordinator may implement one narrow coherent packet directly. Otherwise
   use the fewest fresh writer subagents needed and do not split work merely to
   add concurrency. Give each path exactly one writer. Run packets concurrently
   only when their entire file and command side-effect surfaces are disjoint;
   serialize overlaps, package managers, formatters, code generation,
   migrations, and global checks. The coordinator alone owns staging, commits,
   pushes, GitHub, and Linear.
4. Require each writer to re-read its assigned files before editing and return
   only: completed scope items, files changed, checks and results, blocker, and
   deviation. Writers may not create new product or architecture decisions. If
   a necessary path or command is outside the packet, stop and report it.
5. After every wave, inspect the actual diff, map every hunk to an approved
   step, update the coverage map, and rerun focused checks only when relevant
   state changed. A coherent bounded unit may be committed
   locally with the issue ID, but do not push every wave. Keep an incomplete wave
   local until it is coherent; do not manufacture commits. If a writer fails,
   inspect the workspace before reassigning and never assume it made no changes.
6. Inspect the integrated diff and affected consumers at the exact commit for
   scope fidelity, simplicity and reuse, correctness and failure behavior,
   verification, compatibility, and material resource effects. Delegate only a
   named uncertainty that can change completion; add a specialist only for a
   concrete material risk.
7. Designate one verification owner for the integrated candidate. The
   coordinator may own simple local-logic checks. For any scoped external/native
   protocol, process lifecycle, persistence/concurrency, or producer-consumer
   obligation, use one fresh non-writing default or explorer agent. Give it the
   acceptance contract, exact candidate, changed paths, affected consumers,
   allowed evidence, and obligations—not the author's conclusions. It must
   inspect the code, run the smallest decisive authorized diagnostics, and
   return each obligation as `pass`, `fail`, or `unverified`. Fix failures
   minimally and recheck; `unverified` blocks completion.
8. Reproduce each material finding and route it to the coordinator or owning
   writer for the minimum in-scope correction. Use a non-authoring reviewer to
   recheck judgment-dependent corrections; a deterministic proving check is
   sufficient for a mechanical correction. Do not add arbitrary review rounds.
9. Run the smallest checks proving each acceptance criterion, then only the
   broader repository-supported build, type, lint, and test checks justified by
   the affected surface. For a bug fix, observe the regression check fail against
   the pre-fix behavior when feasible, then pass against the candidate.
10. Reinspect the final diff and Git status. Commit any remaining coherent
   implementation-owned changes with the issue ID and push the final verified
   head normally. Create the one draft PR now if preflight found none. Never
   amend an earlier implementation commit or unrelated history. Require a clean
   worktree and verify the draft PR head equals the final passing commit.

## Completion gate

Call the phase implemented only when:

- every scoped step and acceptance criterion maps to the final diff and passing
  evidence;
- every proof obligation is `pass`; independence-required obligations were run
  by a fresh read-only verifier, and no author claim or author-derived synthetic
  fixture substituted for direct evidence;
- every diff hunk is explained by the scope and non-goals remain untouched;
- relevant build, type, lint, test, and behavior checks pass without an
  unexplained failure;
- realistic failure and compatibility behavior at changed boundaries is
  covered;
- no unnecessary custom code, abstraction, duplication, or evidenced
  performance regression remains when a simpler verified capability exists;
- no unauthorized dependency, interface, migration, cleanup, or external side
  effect beyond the exact branch pushes and draft PR occurred;
- the applicable review axes have no unresolved material finding; and
- the issue branch has a clean, passing final commit; and
- one verified open PR contains that exact commit. It is draft for a new
  implementation; an idempotent retry may observe a later reviewed head or
  published readiness only when those facts are already recorded downstream.

If no edit was made and work cannot proceed, return `blocked`. If implementation
changes exist but a blocker, failed check, interruption, deviation, or finding
prevents a safe commit, preserve the actual changes and return `blocked` with
`result: partial`. Do not publish a Linear implementation comment until the
completion gate passes. If a draft was created before a later block, preserve it
and report its URL and current head so a retry can resume without duplication.

## Linear comment

After the passing commit exists, publish exactly one:

After writing, re-read the comment and return `completed` only if it matches
this schema and contains the evidence required by the completion gate.

```markdown
## Bonaparte · Implementation

**Status:** Implemented

### Review contract
- Outcome: [approved behavior this implementation must deliver]
- Acceptance criteria: [observable criteria carried forward from scope]
- Non-goals: [boundaries the review must preserve]
- Risks and safeguards: [material risks and required safeguards]

### Changed files and responsibilities
| File or boundary | Responsibility delivered | Interfaces/callers affected | Evidence |
|---|---|---|---|
| [`file` or boundary] | [exact change] | [consumer effect or None] | [`file:line`, diff fact, or diagnostic] |

### Evidence ledger
| Criterion | Boundary / owner | Check | Result / evidence |
|---|---|---|---|
| [criterion] | [boundary; coordinator/verifier] | `[exact check]` | [pass/fail/unverified; observed result] |

### Deviations and remaining work
- Deviations: [narrow contract clarification, or “None.”]
- Remaining: [non-blocking follow-up outside this phase, or “None.”]

### Git handoff
- Branch: `[branch]`
- Commit: `[full commit]`
- Draft PR: `[URL]`
- Worktree: clean

```

Publish the review contract, final diff responsibilities, direct proof, and Git
handoff—not the implementation process. Do not include agent identities,
transcripts, tool logs, hash manifests, or unrelated refactoring ideas.

## Receipt

Return only the runner-provided JSON receipt with `phase: implement`. Success
uses `state: completed`, `result: implemented`, the issue identifier and URL,
the exact branch, full commit, and draft PR URL. Clarification uses
`needs-input`. All other incomplete outcomes use `state: blocked`, with
`result: blocked` or `partial` and the safest next action.
