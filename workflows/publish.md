# Tweed Publish

Publish the reviewed Tweed implementation as a ready-to-merge GitHub pull
request and record it in Linear. Use Linear MCP yourself to read the issue and
its Tweed handoffs, and use the installed authenticated `git` and `gh` CLIs for
GitHub. Do not spawn implementation agents, change code, merge, deploy, delete
branches, or mutate anything outside the scoped push, PR, and final Linear
comment.

## Preconditions

- Require solution scope, implementation, and
  `## Tweed · Implementation Review` comments. A bug also requires established
  RCA; a feature does not.
- Extract the exact reviewed branch and commit. Require a clean local worktree
  on that branch, with `HEAD` equal to the reviewed commit.
- Require a configured GitHub `origin`, a working authenticated `gh`, and an
  identifiable default base branch. Ask one question only if the correct base
  branch cannot be discovered.
- If a final Tweed publish comment and matching open PR already exist, return
  that completed result without creating or commenting again only after its
  delivery state and all GitHub facts are re-verified. Otherwise return
  `blocked` and name the missing or stale fact.
- Never force-push, rewrite history, change code, rerun implementation, merge,
  mark a draft PR ready, deploy, or close another PR.

## Publish workflow

1. Read the Linear issue title, URL, and completed Tweed comments. Confirm the
   reviewed commit is a descendant of the implementation commit and that the
   local branch is clean.
2. Discover the GitHub repository and default base branch from `gh` or the
   remote. Confirm the reviewed branch differs from the base and contains the
   intended commits.
3. Search for an existing pull request from the exact head branch. Reuse it when
   it points at the reviewed commit and is open and non-draft. If it is draft,
   blocked, closed, or points somewhere unsafe, return `blocked` rather than
   changing it implicitly.
4. If the branch is not yet published, run an ordinary upstream push to
   `origin`. Never use `--force` or a destructive refspec.
5. Create one non-draft pull request when none exists. Use a concise human title
   derived from the Linear title, prefixed with the issue identifier. The body
   must contain:

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

6. Verify the PR is open, non-draft, targets the discovered base, uses the
   reviewed head branch and commit, and reports no immediately visible creation
   error. Do not claim CI has passed unless GitHub shows it.
7. Add exactly one Linear comment after the PR is verified:

   After writing, re-read the comment and return `completed` only if it matches
   this schema and contains the delivery facts required above.

   ```markdown
   ## Tweed · Pull Request

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
   - Not performed by Tweed: Merge and deployment
   ```

If the push or PR succeeds but the Linear write fails, a retry must recover the
existing PR and add only the missing comment. Never open a duplicate PR.

## Receipt

Return only the runner-provided JSON receipt with `phase: publish`. Success uses
`state: completed`, `result: published`, the issue identifier and Linear URL,
the exact branch and reviewed commit, and the pull request URL. A base-branch
question uses `needs-input`; all other unsafe or incomplete outcomes use
`state: blocked`, `result: blocked`, and the safest next action.
