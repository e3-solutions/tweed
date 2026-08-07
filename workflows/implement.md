# Bonaparte Implementation

Implement the approved Bonaparte scope from the supplied deterministic Linear
handoff using bounded Codex subagents. The runner supplies only the latest scope
or existing implementation result plus issue metadata. Use Linear only to
publish and verify the final handoff. Children must not use Linear. Work only in
the supplied local repository. Create or recover one draft pull request for the
official Linear branch and push only verified implementation commits to it. Do
not mark it ready, merge, deploy, or mutate other remote services or data.

## Contract and safety

- A new implementation requires a complete `## Bonaparte · Solution Scope`; it is
  the complete implementation contract. An `existing` implementation must
  instead carry the complete current implementation schema. Otherwise return
  `blocked` before editing or publishing remote state.
- Treat the scope's outcome, change surface, steps, non-goals, acceptance
  criteria, and validation as the approved contract. Do not redesign or broaden
  it during implementation.
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
   If only the PR handoff is missing, recover or create it from the verified
   existing branch and commit, then publish one refreshed implementation
   handoff; otherwise return `blocked` with the stale fact.
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
   default base branch. Derive one canonical `[host/]owner/repository` selector
   from `origin`; never use ambient `GH_REPO` or infer a repository from the
   working directory. Scope every `gh` read and write explicitly to that
   selector. Require the issue branch to descend from the current remote base and
   reject unrelated commits before pushing.
7. Search all PR states for the exact head branch and inspect every match. Reuse
   exactly one only when its host, head repository, head branch, and base match
   the canonical repository and expected refs. Before implementation completes,
   it must be open and draft. A duplicate, closed, merged, cross-repository, or
   otherwise mismatched PR is ambiguous; return `blocked` without changing it.
8. If no matching PR exists, ensure the issue branch differs from the base. When
   no meaningful implementation commit exists yet, create one verified empty
   kickoff commit containing the issue ID with `git commit --allow-empty --only`
   so staged user work is not consumed. Prove its tree equals its parent, push
   the exact branch with an ordinary upstream push, and create one draft with
   `gh pr create --draft` using explicit `--repo`, `--base`, and `--head`
   arguments. Give it a concise issue-derived title and a body with the Linear
   URL, approved outcome, work-in-progress status, and pending verification.
   Verify its repository, refs, draft state, and URL before any implementation
   wave continues.

## Implementation workflow

1. Translate the approved steps into dependency-aware work packets. Each packet
   must contain its allowed files, required behavior, dependencies, reuse
   decision, non-goals, acceptance criteria, and proving checks.
2. Spawn fresh writer subagents without inherited conversation. Give each path
   exactly one writer. Run packets concurrently only when their entire file and
   command side-effect surfaces are disjoint; serialize overlaps, package
   managers, formatters, code generation, migrations, and global checks.
3. Require each writer to re-read its assigned files before editing and return
   only: completed scope items, files changed, checks and results, blocker, and
   deviation. Writers may not create new product or architecture decisions.
4. After every wave, inspect the actual diff, map every hunk to an approved
   step, and rerun focused checks. When the wave forms a coherent bounded unit,
   stage only its owned files, commit it with the issue ID, and push it normally
   to the draft PR before unlocking dependents. Keep an incomplete wave local
   until it is coherent; do not manufacture commits. If a writer fails, inspect
   the workspace before reassigning and never assume it made no changes.
5. After integration, spawn independent non-authoring reviewers for:
   - **Simplicity, clarity, reuse, and performance:** find code to delete,
     flatten, or replace with verified existing capabilities; reject subjective
     rewrites.
   - **Correctness, robustness, and verification:** falsify changed behavior and
     failure paths; map every acceptance criterion to evidence.
   - **Compatibility and integration:** trace changed interfaces to callers and
     consumers and check supported versions and formats.
   Add a specialist only for a concrete material risk.
6. Reproduce each material finding, route it to the owning writer for the
   minimum in-scope correction, and have a non-authoring reviewer recheck the
   affected surface. Do not add arbitrary review rounds.
7. Run the smallest checks proving each acceptance criterion, then relevant
   repository-supported build, type, lint, and test checks. For a bug fix, add a
   regression check that fails for the original mechanism when feasible.
8. Reinspect the final diff and Git status. Commit any remaining coherent
   implementation-owned changes with the issue ID and push normally. Never amend
   the kickoff, an earlier implementation commit, or unrelated history. Require
   a clean worktree and verify the draft PR head equals the final passing commit.

## Completion gate

Call the phase implemented only when:

- every scoped step and acceptance criterion maps to the final diff and passing
  evidence;
- every diff hunk is explained by the scope and non-goals remain untouched;
- relevant build, type, lint, test, and behavior checks pass without an
  unexplained failure;
- realistic failure and compatibility behavior at changed boundaries is
  covered;
- no unnecessary custom code, abstraction, duplication, or evidenced
  performance regression remains when a simpler verified capability exists;
- no unauthorized dependency, interface, migration, cleanup, or external side
  effect beyond the exact branch pushes and draft PR occurred;
- independent reviewers have no unresolved material finding; and
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

### Review contract
- Outcome: [approved behavior this implementation must deliver]
- Acceptance criteria: [observable criteria carried forward from scope]
- Non-goals: [boundaries the review must preserve]
- Risks and safeguards: [material risks and required safeguards]

### Delivered behavior
- [Observable behavior] → [scope item/acceptance criterion] → [files]

### Changed files and responsibilities
| File or boundary | Responsibility delivered | Interfaces/callers affected | Evidence |
|---|---|---|---|
| [`file` or boundary] | [exact change] | [consumer effect or None] | [`file:line`, diff fact, or diagnostic] |

### Verification
| Command or diagnostic | Result | Scope/criterion proved | Relevant boundary |
|---|---|---|---|
| `[exact command or diagnostic]` | [pass/fail and salient counts] | [criterion] | [files/interface] |

### Review findings
| Finding | Evidence and consequence | Disposition/fix | Recheck |
|---|---|---|---|
| [Finding or None] | [file/runtime evidence] | [fixed/rejected and why] | [proof] |

### Deviations
[Narrow clarification, or “None.”]

### Remaining work
[Non-blocking follow-up outside this phase, or “None.”]

### Git handoff
- Branch: `[branch]`
- Commit: `[full commit]`
- Draft PR: `[URL]`
- Worktree: clean

### Implementation map
| Role | Material conclusion | Evidence | Affected surface | Confidence | Relationship |
|---|---|---|---|---|---|
| [Agent role] | [substantive authored/review finding] | [`file:line` or diagnostic] | [files/boundary] | [high/medium/low and why] | [authored/reviewed/challenged] |

**Synthesis:** [How scope items map to the commit and passing evidence, how
material findings were resolved, and why review can begin from this comment.]
```

Include every writer and reviewer once. Do not include transcripts, tool logs,
hash manifests, or unrelated refactoring ideas.

## Receipt

Return only the runner-provided JSON receipt with `phase: implement`. Success
uses `state: completed`, `result: implemented`, the issue identifier and URL,
the exact branch, full commit, and draft PR URL. Clarification uses
`needs-input`. All other incomplete outcomes use `state: blocked`, with
`result: blocked` or `partial` and the safest next action.
