# Bonaparte Publish

Finalize the reviewed Bonaparte draft pull request, mark it ready for review, and
record it in Linear. The runner supplies only the latest review or existing
publish result plus issue metadata. Use authenticated `git` and `gh` for GitHub.
Do not spawn subagents, change code, push commits, create another PR,
merge, deploy, delete branches, or mutate anything outside the existing PR's
metadata, readiness, and final Linear comment.

## Preconditions

- Existing publish result: reverify its exact ready PR and Linear delivery
  comment, then return it without another write when they still match. When the
  runner also supplies a newer complete review for the same open PR and branch,
  require its reviewed commit to be a clean descendant of the recorded publish
  commit, validate it with the normal publish gate, and update
  `existing_comment_id` in place after the gate passes. Never add a duplicate
  delivery comment. A changed PR or branch, non-descendant commit, missing
  review, dirty worktree, or unverifiable ancestry remains blocked.
- New publish: require a complete `## Bonaparte · Implementation Review` as the
  publish handoff.
- Extract the exact reviewed branch and commit. Require a clean local worktree
  on that branch, with `HEAD` equal to the reviewed commit.
- Require a configured GitHub `origin`, a working authenticated `gh`, and an
  identifiable base named by trusted supplemental input or, when absent,
  GitHub's default base. Derive one canonical `[host/]owner/repository` selector
  from `origin`; never use ambient `GH_REPO` or infer a repository from the
  working directory. Scope every `gh` read and write explicitly to that
  selector. Ask one question only if the base cannot be discovered.
- For a new publish, require the review handoff's draft PR URL. Verify it belongs
  to that canonical repository, is open, uses the exact reviewed head branch and
  expected base, and points at the reviewed commit. It should be draft unless an
  interrupted publish satisfies the exact recovery checks in step 3. A missing,
  duplicate, closed, merged, unexpectedly non-draft, or mismatched PR is unsafe;
  return `blocked` without changing it.

## Publish workflow

Before each write, revalidate the exact target identity and stop if it changed;
read back every write so an interrupted retry can continue idempotently.

1. Read the supplied review and issue metadata. Confirm the reviewed commit is
   a descendant of the implementation commit and that the local branch is
   clean.
2. Resolve the canonical GitHub repository and expected base from `origin` and
   the trusted supplemental input, falling back to GitHub's default base.
   Confirm the reviewed branch differs from the base, contains the implementation
   commit, and has no local commit beyond the PR head.
3. Resolve the exact PR by the review handoff URL and head branch. Search all PR
   states for that branch to reject duplicates, then re-verify its repository,
   base, head branch, and head commit before any mutation. If it is already
   non-draft at the reviewed commit, treat readiness as completed remote state
   from an interrupted publish only when its title contains the issue identifier
   and its body contains the required sections and Linear link.
4. While the exact PR is still draft, update it with a concise human title
   derived from the Linear title, prefixed with the issue identifier, and a body
   containing:

   ```markdown
   ## Summary
   - [What user-visible problem this fixes]

   ## Changes
   - [Main implementation responsibility]

   ## Verification
   - [Exact checks reported by implementation/review]

   ## Linear
   - [Issue identifier and URL]
   ```

5. If the exact PR is still draft, mark it ready for review. Never change the
   readiness or metadata of another PR.
6. Verify the PR is open, non-draft, targets the expected base, uses the exact
   canonical head repository, reviewed branch, and reviewed commit, and reports
   no immediately visible update error. Do not claim CI has passed unless GitHub
   shows it.
7. Create exactly one Linear comment after the PR is verified, or update the
   supplied `existing_comment_id` in place when reconciling a reviewed descendant:

   After writing, re-read the comment and return `completed` only if it matches
   this schema and contains the delivery facts required above.

   ```markdown
   ## Bonaparte · Pull Request

   **Status:** Ready for review

   ### Delivery
   - Pull request: [URL]
   - Pull request state: Open and non-draft
   - Branch: `[branch]`
   - Reviewed commit: `[full commit]`
   - Base: `[base branch]`
   - CI: [observed status, or “Pending/not observed”]

   ### Final delivery state
   - Delivered contract: [concise issue outcome from the reviewed handoff]
   - Remaining conditions: [CI, approvals, or “None observed”]
   - Not performed by Bonaparte: Merge and deployment
   ```

If PR finalization succeeds but the Linear write fails, a retry must recover the
same ready PR and add only the missing comment or update only the supplied stale
comment. Never open a duplicate PR.

## Completion gate

Complete only when the exact PR is open and non-draft at the reviewed commit,
its repository/base/head match, its title and required body sections identify the
issue, local `HEAD` and clean worktree are unchanged, and one verified Linear
delivery comment records it. Never duplicate that comment or claim ready to
merge while CI or approvals remain pending or unobserved.

## Receipt

Return only the runner-provided JSON receipt with `phase: publish`. Success uses
`state: completed`, `result: published`, the issue identifier and Linear URL,
the exact branch and reviewed commit, and the pull request URL. A base-branch
question uses `needs-input`; all other unsafe or incomplete outcomes use
`state: blocked`, `result: blocked`, and the safest next action.
