# Tweed Publish

Publish the reviewed Tweed implementation by updating its draft GitHub pull
request, marking it ready for review, and recording it in Linear. Use Linear MCP
yourself to read the issue and its Tweed handoffs, and use the installed
authenticated `git` and `gh` CLIs for GitHub. Do not spawn implementation
agents, change code, merge, deploy, delete branches, or mutate anything outside
the scoped push, PR finalization, and final Linear comment.

## Preconditions

- Require solution scope, implementation, and
  `## Tweed · Implementation Review` comments. A bug also requires established
  RCA; a feature does not.
- Extract the exact reviewed branch and commit. Require a clean local worktree
  on that branch, with `HEAD` equal to the reviewed commit.
- Require a configured GitHub `origin`, a working authenticated `gh`, and an
  identifiable default base branch. Ask one question only if the correct base
  branch cannot be discovered.
- Require the implementation handoff's PR URL and confirm it is open, targets
  the expected base, and uses the exact reviewed head branch. It should be draft
  unless an interrupted publish already marked it ready. For compatibility with
  an older handoff that has no PR URL, search by exact head branch and recover
  the matching open PR or create one draft after pushing.
- If a final Tweed publish comment and matching open non-draft PR already exist,
  return that completed result without creating or commenting again.
- Never force-push, rewrite history, change code, rerun implementation, merge,
  deploy, close another PR, or change an unrelated PR.

## Publish workflow

1. Read the Linear issue title, URL, and completed Tweed comments. Confirm the
   reviewed commit is a descendant of the implementation commit and that the
   local branch is clean.
2. Discover the GitHub repository and default base branch from `gh` or the
   remote. Confirm the reviewed branch differs from the base and contains the
   intended commits.
3. Resolve the implementation draft PR by its recorded URL and exact head
   branch. If an older handoff has no draft, search by the exact head branch;
   reuse only one matching open PR. A closed, merged, mismatched, or duplicate PR
   is ambiguous, so return `blocked` without changing it. If the matching PR is
   already non-draft, require it to point at the exact reviewed commit and treat
   its readiness as completed remote state from an interrupted or legacy run.
4. Push the reviewed head to the existing branch with an ordinary upstream push
   to `origin`. Never use `--force` or a destructive refspec. When a PR already
   exists, verify it now points at the reviewed commit.
5. When the PR is still draft, update it with a concise human title derived from
   the Linear title, prefixed with the issue identifier, and a body containing:

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

   If compatibility recovery found no PR, create it as a draft with this title
   and body after the push. Then mark the exact draft ready for review. If the
   exact PR is already non-draft, do not change it again. Never alter the
   readiness of any other PR.
6. Verify the PR is open, non-draft, targets the discovered base, uses the
   reviewed head branch and commit, and reports no immediately visible update
   error. Do not claim CI has passed unless GitHub shows it.
7. Add exactly one Linear comment after the PR is verified:

   ```markdown
   ## Tweed · Pull Request

   **Status:** Ready to merge

   - Pull request: [URL]
   - Branch: `[branch]`
   - Reviewed commit: `[full commit]`
   - Base: `[base branch]`
   - CI: [observed status, or “Pending/not observed”]
   ```

If the push or PR succeeds but the Linear write fails, a retry must recover the
existing PR and add only the missing comment. Never open a duplicate PR.

## Receipt

Return only the runner-provided JSON receipt with `phase: publish`. Success uses
`state: completed`, `result: published`, the issue identifier and Linear URL,
the exact branch and reviewed commit, and the pull request URL. A base-branch
question uses `needs-input`; all other unsafe or incomplete outcomes use
`state: blocked`, `result: blocked`, and the safest next action.
