# Tweed Implementation

Implement the approved Tweed scope from the supplied Linear issue using bounded
Codex subagents. Use Linear MCP yourself to read the issue, its Tweed scope, and
its RCA when the issue is a bug; check for an existing implementation handoff
and publish the final handoff. Children must not use Linear. Work only in the
supplied repository. Create or recover the issue branch's draft pull request as
the implementation kickoff, but do not mark it ready, merge, deploy, or mutate
other remote services or data.

## Contract and safety

- Require a complete `## Tweed · Solution Scope`. A bug also requires an
  established `## Tweed · Root Cause Analysis`; a feature does not. Otherwise
  return `blocked` before editing.
- Treat the scope's outcome, change surface, steps, non-goals, acceptance
  criteria, and validation as the approved contract. Do not redesign or broaden
  it during implementation.
- Prefer the scope's verified project utilities, built-ins, and installed
  dependencies. Add a dependency, lockfile change, schema, migration, public
  interface, generated asset, or configuration only when explicitly required.
- Never overwrite, discard, stash, reset, clean, or attribute pre-existing user
  work to Tweed. Never use destructive Git commands.
- Local file edits, local validation, branch creation, staging, and committing
  are allowed. Linear may be written only after a passing implementation commit
  exists.
- The only allowed GitHub writes are ordinary non-force pushes of the issue
  branch and creation of one draft pull request for that exact branch. Reuse the
  same branch and PR on retries. Credentials, live migrations, production
  checks, PR readiness, merging, and deployment belong to later phases.

## Preflight

1. Read the durable Linear handoff. If a comment already begins with
   `## Tweed · Implementation`, verify its branch and commit still exist locally
   and its recorded PR remains open for the exact head branch, whether it is
   still draft or was later published. Then return that completed result without
   reimplementing.
2. Record repository identity, current branch, `HEAD`, staged, unstaged, and
   untracked paths. Derive a human branch named
   `tweed/<issue-id>-<short-title-slug>`.
3. If the worktree is clean, create or switch to that issue branch without
   rewriting history. Reuse an existing issue branch only when its ancestry and
   contents are consistent with this issue.
4. If the expected issue branch contains uncommitted work from an interrupted
   attempt, continue only when every changed path and hunk can be mapped to the
   approved scope. Otherwise return `blocked` and preserve it exactly. Any
   unrelated dirty state blocks automatic implementation.
5. If the clean issue branch already contains a non-empty issue-labeled commit
   beyond the kickoff but no Linear implementation comment, treat it as a
   candidate from an interrupted attempt. Reuse it only when its complete diff
   maps to the scope and, if already pushed, the draft PR points at that exact
   commit. Rerun the required validation and reviews before recording the
   handoff; do not duplicate the edit or commit.
6. Verify that the scoped files, interfaces, dependencies, and tests still
   match current repository behavior. Return `blocked` when the scope is
   materially stale or requires an external action beyond the permitted GitHub
   kickoff to pass.
7. Require a configured GitHub `origin`, authenticated `gh`, and an identifiable
   default base branch. Confirm the issue branch differs from the base. Search
   for a pull request with that exact head branch and reuse it only when it is
   open and draft. A non-draft, closed, merged, or mismatched PR is ambiguous;
   return `blocked` without changing it.
8. If no PR exists, ensure the branch has a commit beyond the base by creating
   one empty kickoff commit containing the issue ID when necessary. Push the
   exact branch with an ordinary upstream push, never `--force` or a destructive
   refspec, then run `gh pr create --draft`. Use a concise issue-derived title
   and a body containing the issue link, approved outcome, implementation-in-
   progress status, and pending verification. Verify that the resulting PR is
   open, draft, targets the default base, and uses the exact issue branch.

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
   step, rerun focused checks when feasible, and only then unlock dependents. If
   a writer fails, inspect the workspace before reassigning; never assume it
   made no changes.
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
8. Reinspect the final diff and Git status. Stage only implementation-owned
   files and create one implementation commit with a concise message containing
   the issue ID, unless preflight recovered that exact commit from an interrupted
   attempt. Do not amend the kickoff or unrelated commits. Require a clean
   worktree after committing. Push the implementation commit with an ordinary
   non-force push and verify the draft PR's head is that exact commit. Review
   may add a later local correction commit before publish pushes the reviewed
   head.

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
  effect beyond the exact branch push and draft PR occurred;
- independent reviewers have no unresolved material finding; and
- the issue branch has a clean, passing implementation commit; and
- one verified open draft PR points from the exact implementation commit on the
  issue branch to the default base.

If no edit was made and work cannot proceed, return `blocked`. If implementation
changes exist but a blocker, failed check, interruption, deviation, or finding
prevents a safe commit, preserve the actual changes and return `blocked` with
`result: partial`. Do not publish a Linear implementation comment until the
completion gate passes. If kickoff succeeded before a later block, preserve and
report the branch, kickoff commit, and draft PR so a retry can resume them.

## Linear comment

After the passing commit exists, publish exactly one:

```markdown
## Tweed · Implementation

### Delivered
- [Scope item or acceptance criterion] → [files]

### Changes
- [`file` or component]: [responsibility changed]

### Verification
- `[exact command or diagnostic]` → [result and criterion proved]

### Review findings
- [Finding] → [fixed/rejected] because [evidence]

### Deviations
[Narrow clarification, or “None.”]

### Remaining work
None.

### Git handoff
- Branch: `[branch]`
- Commit: `[full commit]`
- Draft PR: `[URL]`
- Worktree: clean

### Implementation map
- [Agent role] — [authored/reviewed/challenged]: [one-line result]
- Synthesis — implemented: [why the gate passed]
```

Include every writer and reviewer once. Do not include transcripts, tool logs,
hash manifests, or unrelated refactoring ideas.

## Receipt

Return only the runner-provided JSON receipt with `phase: implement`. Success
uses `state: completed`, `result: implemented`, the issue identifier and URL,
the exact branch, full implementation commit, and draft PR URL. Clarification
uses `needs-input`. All other incomplete outcomes use `state: blocked`, with
`result: blocked` or `partial` and the safest next action.
