# Bonaparte Publish

Finalize the reviewed Bonaparte draft pull request, mark it ready for review, and
record it in Linear. The runner supplies only the latest review or existing
publish result plus issue metadata. Use Linear only to publish and verify the
final comment, and use the installed authenticated `git` and `gh` CLIs for
GitHub. Do not spawn implementation agents, change code, push commits, create
another PR, merge, deploy, delete branches, or mutate anything outside the
existing PR's metadata, readiness, and final Linear comment.

## Preconditions

- If an `existing` publish result was supplied, validate its complete delivery
  state and matching open PR before returning it. Otherwise require a complete
  `## Bonaparte · Implementation Review`; it is the complete publish handoff.
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
  interrupted publish already marked it ready. A missing, duplicate, closed,
  merged, or mismatched PR is unsafe; return `blocked` without changing it.
- When an `existing` publish result was supplied, return it without another
  comment only after its delivery state and all GitHub facts are re-verified;
  otherwise return `blocked` and name the missing or stale fact. When a review
  handoff was supplied, continue with the finalization workflow below.
- Never force-push, rewrite history, change code, rerun implementation, merge,
  create another PR, deploy, or close or change another PR.

## Publish workflow

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
   from an interrupted publish.
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
7. Add exactly one Linear comment after the PR is verified:

   After writing, re-read the comment and return `completed` only if it matches
   this schema and contains the delivery facts required above.

   ```markdown
   ## Bonaparte · Pull Request

   **Status:** Ready to merge

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
same ready PR and add only the missing comment. Never open a duplicate PR.

## Receipt

Return only the runner-provided JSON receipt with `phase: publish`. Success uses
`state: completed`, `result: published`, the issue identifier and Linear URL,
the exact branch and reviewed commit, and the pull request URL. A base-branch
question uses `needs-input`; all other unsafe or incomplete outcomes use
`state: blocked`, `result: blocked`, and the safest next action.
