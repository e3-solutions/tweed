# Tweed Requirements Specification

Status: Draft v0.4
Last updated: 2026-08-01

## 1. Purpose

Tweed is a strict Linear-backed Codex workflow for delivering one software
change through fresh, isolated phase coordinators.

```text
Problem issue → RCA → scope → implement → review → ready to merge
Feature issue → scope → implement → review → ready to merge
```

Every request begins as a real Linear issue. Linear is the durable baton between
phases; downstream coordinators never inherit prior phase conversations.

## 2. V1 interface

```text
tweed create problem <request>
tweed create feature <request>
tweed root-cause <issue>
tweed scope <issue>
tweed implement <issue>
tweed review <issue>
tweed resume <run> <answer>
tweed retry-sync <run>
```

Each phase command performs at most one legal stage transition. V1 has no
automatic multi-phase command, arbitrary workflow graph, child-ticket creation,
dashboard, deployment, or merge command.

## 3. Core invariants

### 3.1 One request, one canonical issue

`create` creates or recovers exactly one intake issue using a durable Tweed run
ID. A problem begins at `needs-rca`; a feature begins at `needs-scope`. All
completed phases update the same issue.

### 3.2 One legal next stage

| Kind | Current stage | Command | Completed status | Next stage |
|---|---|---|---|---|
| Problem | `needs-rca` | `root-cause` | `established` | `needs-scope` |
| Problem or feature | `needs-scope` | `scope` | `scoped` | `ready-to-implement` |
| Problem or feature | `ready-to-implement` | `implement` | `implemented` | `ready-to-review` |
| Problem or feature | `ready-to-review` | `review` | `reviewed` | `ready-to-merge` |

The runner rejects every other combination before repository mutation. A
`blocked`, `partial`, `not-established`, failed, interrupted, or `needs-input`
result never advances the issue.

### 3.3 History is not context

Each phase starts a fresh Codex thread. It receives only:

- The exact current Linear issue snapshot.
- The target repository or integration worktree.
- Its phase workflow.
- A clarification answer when resuming that same phase.

Raw agent transcripts, tool calls, rejected exploration, and parent
conversations do not cross phase boundaries.

### 3.4 Evidence outranks self-report

A phase status alone is insufficient. Its report must contain repository,
runtime, test, or other auditable evidence required by its completion gate.
Implementation and review evidence must refer to the exact recorded commit.

### 3.5 One writer

Only the runner's narrow Linear writer may update the canonical issue. Only one
implementation or review writer may mutate a repository at a time. Agents never
commit, push, open pull requests, merge, or deploy.

## 4. Linear issue format

The issue description contains one versioned metadata block and deterministic
phase sections.

````markdown
<!-- tweed:metadata:start -->
## Tweed

```json
{
  "schema_version": 1,
  "kind": "problem",
  "stage": "needs-rca",
  "contract_revision": 0,
  "repository": "/absolute/repository",
  "planning_base": "git-sha",
  "integration_branch": null,
  "integration_commit": null,
  "linear_project": "Project",
  "last_run": "tw_..."
}
```
<!-- tweed:metadata:end -->

<!-- tweed:request:start -->
# Request

[Original request without reinterpretation.]
<!-- tweed:request:end -->
````

Later phases add exactly one `rca`, `scope`, `implementation`, or `review`
section using the same markers. Re-running synchronization replaces the same
section rather than appending another copy.

The runner composes the complete Markdown description deterministically. The
Linear writer receives exact desired Markdown and does not summarize or rewrite
it.

## 5. Linear boundaries

Each phase uses three capability boundaries:

```text
narrow Linear reader → phase coordinator → narrow Linear writer
```

The reader retrieves one exact issue snapshot and performs no writes. The
coordinator receives the frozen snapshot and performs no Linear writes. After a
completion gate passes, the writer:

1. Re-reads exactly the expected issue.
2. Accepts an already-applied identical description as an idempotent success.
3. Otherwise verifies the old description digest.
4. Replaces the description exactly once.
5. Reads the issue back and verifies the result.

A digest mismatch blocks synchronization. It never overwrites concurrent user
or Tweed changes.

V1 creates no milestone comments and writes no drafts, questions, failures,
partial results, agent activity, or transcripts to Linear.

## 6. Intake

`create` requires:

- Kind: `problem` or `feature`.
- Original request.
- Canonical Git repository path.
- Current `HEAD` as the planning base.
- Configured Linear project.
- Unique Tweed run ID.

The create writer searches for the run ID before creating an issue. Retrying the
same run must recover the existing issue rather than creating a duplicate.

## 7. Root-cause phase

Root-cause analysis is valid only for a problem at `needs-rca`.

It may return `established`, `not-established`, `blocked`, or `needs-input`.
`established` requires evidence for:

- Triggering condition.
- Responsible code, configuration, data, dependency, or environment boundary.
- Causal mechanism.
- Rejection of the strongest credible alternative.

Only `established` writes the RCA section and advances to `needs-scope`.

## 8. Scope phase

Scope is valid only at `needs-scope`. A problem requires an established RCA; a
feature proceeds from the original request and verified repository behavior.

It may return `scoped`, `blocked`, or `needs-input`. `scoped` requires:

- Observable outcome.
- Smallest coherent scope and explicit non-goals.
- Verified repository fit and reuse decisions.
- Interfaces, failures, compatibility, and material risks.
- Binary acceptance criteria.
- Ordered implementation plan and validation.

Only `scoped` writes the scope section, refreshes the planning base, and
advances to `ready-to-implement`.

## 9. Implementation phase

Implementation is valid only at `ready-to-implement`.

Before starting, the runner:

1. Requires the source checkout to be clean.
2. Acquires the repository writer lock.
3. Creates or opens `tweed/<issue>` in an isolated sibling worktree from the
   recorded planning base.

The coordinator may modify only that worktree and may use read-only agents in
parallel. V1 serializes all writers. It may return `implemented`, `partial`,
`blocked`, or `needs-input`.

`implemented` requires every acceptance criterion to map to the final diff and
passing evidence, with no unexplained check failure or scope deviation. The
runner then stages and commits the complete isolated worktree. Only a successful
commit allows the implementation section, branch, and commit to be recorded and
the issue to advance to `ready-to-review`.

## 10. Review phase

Review is valid only at `ready-to-review`. The runner requires the recorded
integration worktree to be clean and at the recorded implementation commit.

Independent reviewers challenge scope fidelity, simplicity and reuse,
correctness and robustness, compatibility, performance where relevant, and
verification quality. Reviewers do not edit. A bounded fixer may apply only an
accepted in-scope correction, after which a non-authoring reviewer rechecks it.

Review may return `reviewed`, `partial`, `blocked`, or `needs-input`.
`reviewed` requires zero unresolved material findings and passing final checks.
The runner commits any corrections, verifies a clean worktree, records the exact
final commit, writes the review section, and advances to `ready-to-merge`.

## 11. Clarification

A phase asks at most one material question at a time. A question must contain:

- Exact decision.
- Why it materially affects the phase.
- Up to three concrete options when applicable.
- Evidence-backed recommendation when available.

The runner persists the run, issue digest, workflow snapshot, child thread ID,
worktree, and question before returning `needs-input`. `resume` verifies that
the Linear issue has not changed and resumes the same child thread. Answers are
normalized into the completed phase report, not copied as conversation.

## 12. Recovery and receipts

Run state and full reports live privately under the XDG state directory with
atomic writes and owner-only permissions. A completed report is persisted before
Linear synchronization.

If synchronization fails or its acknowledgement is lost, `retry-sync` retries
only the idempotent Linear operation. It never reruns the phase or creates a new
implementation commit.

Agent mode emits exactly one versioned JSON receipt, including failures. It is
limited to 4 KiB and contains only run, issue, phase, stage, summary, question,
thread, branch, commit, and error fields. It never includes a complete report or
raw task output.

## 13. Ready-to-merge boundary

`ready-to-merge` means:

- The issue contains the completed request, RCA when applicable, scope,
  implementation, and review handoffs.
- The integration branch points to the recorded final commit.
- The worktree is clean.
- Required validation and independent review passed against that commit.
- No material finding or scope deviation remains.

Tweed v1 stops there. Pushing, opening a pull request, merging, releasing, and
deploying require separate explicit authorization and tooling.

## 14. V1 acceptance scenarios

1. Creating a problem produces one issue at `needs-rca`.
2. Creating a feature produces one issue at `needs-scope`.
3. A wrong-stage command performs no repository or Linear write.
4. A clarification resumes the same child thread and does not advance early.
5. Every successful phase performs exactly one deterministic section update and
   one legal stage transition.
6. Retrying creation or synchronization cannot duplicate the issue or phase
   section.
7. Concurrent issue modification blocks synchronization.
8. Implementation and review occur on the runner-owned issue worktree.
9. Only a clean, reviewed, tested commit reaches `ready-to-merge`.
10. The parent Codex context receives only bounded receipts and questions.
11. A Tweed child cannot recursively invoke Tweed.
