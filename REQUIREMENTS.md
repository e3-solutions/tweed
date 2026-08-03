# Tweed Requirements Specification

Status: Draft v0.5
Last updated: 2026-08-03

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

## 4. Linear issue and journal format

The issue description contains the complete visible original request, a stable
human-readable explanation that phase handoffs live in comments, and one
canonical base64url protocol token containing the exact UTF-8 request and
genesis metadata. Tweed never rewrites the description after intake.

````markdown
[Original request without reinterpretation.]

---

Tweed phase handoffs are appended as human-readable comments.

`tweed-genesis-v2:<canonical-base64url-token>`
````

The token metadata includes a digest of the exact request. Valid legacy
descriptions with contiguous phase sections are adopted as a deterministic
virtual journal prefix without changing their prose.

Each later phase appends exactly one top-level Linear comment. Its visible body
is the complete human-readable report. A strict machine envelope records the
protocol, deterministic comment ID, issue and run identity, phase/status, legal
from/to stages, exact artifact digest, predecessor and genesis digests, and
repository/base/branch/commit provenance. The record digest binds canonical
envelope bytes and exact UTF-8 report bytes. The exact values are carried in a
canonical token so Linear may normalize visible Markdown without making a
completed reasoning phase run again.

## 5. Linear boundaries

Each phase uses three capability boundaries:

```text
narrow Linear reader → phase coordinator → narrow Linear writer
```

The reader and writer are deterministic operations of the bundled
`dev.tweed.linear.v2` adapter, never Codex/model sessions. It uses the officially
supported personal `LINEAR_API_KEY` path for this local personal script. Tweed
never discovers or extracts connector credentials. An optional adapter override
is retained for hermetic tests and compatible installations.
The runner blanks both Linear authentication and adapter configuration in every
Codex/model child environment.

The reader retrieves one exact issue snapshot and performs no writes. The
coordinator receives the frozen snapshot and performs no Linear writes. After a
completion gate passes, the writer:

1. Fetches and validates the complete bounded comment chain.
2. Recovers an exact existing deterministic run/phase comment idempotently.
3. Otherwise requires the frozen content snapshot and unique predecessor head.
4. Creates the deterministic comment once.
5. Re-fetches the complete chain and requires the exact unique desired head.

Malformed markers, edits/archives, bad hashes, dangling records, conflicting
duplicates, forks, illegal transitions, or stale content block synchronization.
Human prose is never overwritten.

Each phase fetches and persists one complete authoritative snapshot. All phase
work uses that frozen artifact. Resume performs only a cheap revision/digest
verification; publication uses the frozen content and predecessor digests as
fail-closed preconditions and validates again afterward.

Linear documents ordinary comment creation but no predecessor-conditioned
mutation. Tweed therefore makes no server-side atomic-CAS claim. Cross-host
siblings can create a detectable fork. Comments are editable/deletable: Tweed
detects all malformed or changed present records and rollback relative to a
persisted frozen head, but a fresh client cannot prove that a deleted tail once
existed. No documented public API supplies that missing historical anchor.

Tweed writes no drafts, questions, failures, partial results, agent activity,
or transcripts to Linear.

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
Linear synchronization. Repository-writing phases also persist a `finalizing`
checkpoint before committing; resume either completes the pending commit or
adopts only the exact clean single-child Tweed commit, then synchronizes without
starting Codex again.

Request, RCA, scope, implementation, review, and evidence bodies are separate
content-addressed artifacts. A versioned manifest records each path, SHA-256,
byte length, and media type. Phase prompts carry only bounded phase-specific
artifact references; agents verify and open a referenced artifact on demand.
The runner materializes a complete local phase view from the protected request
and validated journal while Linear itself retains the complete reports as
readable comments. Existing run state is migrated lazily with an immutable
backup. A pending legacy description-CAS synchronization is preserved but fails
closed because its ambiguous remote outcome cannot safely be translated into a
journal append.

Deterministic evidence may be reused only when the complete cache key matches:
repository commit/index/worktree identity, exact command arguments, dependency
and lockfile digests, relevant configuration, declared environment inputs,
tool/runtime versions, execution controls including timeout, and referenced
artifact hashes. Uncertainty recomputes.
Reviewer reasoning and targeted re-review are never cacheable substitutes.

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
