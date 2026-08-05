# Tweed Bug RCA

Investigate the bug recorded in the supplied Linear issue and publish one
evidence-backed root cause analysis as its first Tweed comment. Use Linear MCP
yourself to read the issue and write the final comment. Keep all repository
investigation in isolated subagents so the invoking task receives only the
bounded receipt.

## Durable phase boundary

- This is a fresh phase coordinator. Its only request-specific input is the
  Linear issue identifier. Read the issue description and completed Tweed
  comments from Linear; do not expect or request inherited coordinator or
  subagent context, a prior report in the prompt, hidden files, or local phase
  state.
- The JSON receipt is control-plane data only. Never treat its summary as a
  handoff or put report content in it. Resuming this coordinator after
  `needs-input` is the only within-phase context exception.
- Before returning `completed`, publish and re-read the Linear comment. It must
  contain every material fact the scope phase will need without access to this
  coordinator's context. If the write cannot be verified or the comment is
  incomplete, do not return `completed`.

## Boundaries

- The input must identify an existing Linear bug issue. If it does not, return
  `needs-input`; never create or guess an issue. If the issue is a feature,
  return `blocked` because features proceed directly to scope.
- The coordinator may use Linear only to read the issue, check for a prior Tweed
  RCA comment, and publish the final comment. Children must not use Linear.
- Do not change the issue title or description, modify project files, install
  dependencies, add helper code, create a branch, propose a fix, or implement
  anything.
- Use existing repository tools, tests, history, logs, and configuration.
- Treat the issue report as a symptom, not as a proven explanation.
- Prefer runtime, test, repository, configuration, and history evidence over
  agent opinion.
- Inspect available evidence before asking the user. Ask only when one material
  fact cannot be discovered from the repository or issue.

## Investigation workflow

1. Read the Linear issue and record the exact reported behavior, expected
   behavior when known, affected surface, reproduction details, environment,
   constraints, and supplied evidence. Do not silently fill gaps.
2. Record the absolute repository path, Git `HEAD`, and whether the worktree is
   clean or dirty. Treat dirty and untracked files as live state rather than as
   evidence from `HEAD`, and disclose when they affect the finding.
3. Spawn independent read-only investigators, without inherited conversation,
   for the distinct jobs the problem requires. Usually cover:
   - reproduction or precise symptom characterization;
   - execution-path, state, configuration, dependency, and history tracing; and
   - falsification of the leading explanation and strongest credible
     alternative.
4. Run independent work concurrently when possible, or in blind waves. Give
   each child only the issue facts, repository path, its assignment, the
   read-only boundary, and the evidence standard. Do not reveal another
   investigator's conclusion before its first return.
5. Require each return to be at most 500 words and contain only:

   ```text
   Conclusion: precise claim
   Evidence: diagnostic result and file:line references
   Confidence: high | medium | low, with reason
   Missing: missing evidence or none
   Relationship: supports | challenges | unresolved
   ```

   In the final synthesis, retain every material conclusion with its evidence,
   affected files or boundary, objection or risk, confidence, and unresolved
   gap. Do not copy a transcript or tool log.

6. Reconcile the independent results. Identify the best-supported causal chain,
   the strongest credible alternative, contradictions, and the exact evidence
   still missing from the completion gate.
7. Use a targeted follow-up investigator only when a concrete diagnostic can
   resolve a named gap or contradiction. Share relevant claims and evidence,
   not raw transcripts. Do not add agents or rounds that cannot change the
   conclusion.
8. Immediately before reporting, re-read every cited code location and rerun
   the smallest confirming diagnostic when feasible. If relevant repository
   state changed during the investigation, reconcile the conclusion against the
   new state.

## Completion gate

Call the root cause established only when direct evidence identifies all four:

- the triggering condition;
- the responsible code, configuration, data, dependency, or environment
  boundary;
- the mechanism connecting that trigger to the observed failure; and
- why the strongest credible alternative does not fit the evidence.

The completed Linear handoff must also name the affected boundaries and files,
separate reproduction/runtime evidence from repository/configuration/history
evidence, record every strong alternative actually checked, disclose all
material uncertainty, and consolidate the investigation map into substantive
evidence-bearing conclusions. A correct diagnosis in coordinator context is
not complete until those facts are present in the verified Linear comment.

Direct evidence can include a reproduction, execution trace, failing test,
focused diagnostic, logs, telemetry, or configuration/history records. A
plausible theory, code smell, or investigator consensus is not enough.

If one user answer could close the evidence gap, return `needs-input` with one
concise question. Use `summary` to explain why it matters and `next_action` for
concrete options or an evidence-backed recommendation. Do not write a Linear
comment yet. If repository work cannot establish the cause and no single answer
will do so, report `not-established` and name the smallest next diagnostic.

## First Tweed comment

For terminal `established` or `not-established` results, check whether an
existing comment begins with `## Tweed · Root Cause Analysis`. Reuse it only if
it satisfies the current completion gate and self-contained schema; otherwise
return `blocked` and name the missing durable handoff facts rather than
duplicating or silently accepting it. Otherwise add exactly one comment in this
form:

```markdown
## Tweed · Root Cause Analysis

**Status:** Established | Not established

### Root cause
[Precise causal statement, or “Root cause not established.”]

### Problem definition
[Observed behavior, expected behavior, affected surface, and triggering
conditions now known.]

### Causal chain
1. [Trigger]
2. [Responsible boundary and mechanism]
3. [Observed failure]

### Evidence

#### Reproduction and runtime
- [Reproduction, focused diagnostic, trace, log, or runtime result and what it proves]

#### Repository, configuration, and history
- [`file:line`, configuration, dependency, or history evidence and what it proves]

### Affected boundaries and files
- [`path` or external boundary]: [responsibility, failure contribution, and affected callers/consumers]

### Alternatives checked
| Alternative | Evidence tested | Result | Why weaker than the conclusion |
|---|---|---|---|
| [Strong credible alternative] | [diagnostic or repository evidence] | [rejected/unresolved] | [reason] |

### Remaining uncertainty
[Material unknowns, or “None.”]

### Repository state
- Repository: [absolute path]
- HEAD: [commit, or “not a Git repository”]
- Worktree: [clean or relevant dirty/untracked state]

### Investigation map
| Role | Material conclusion | Evidence | Affected surface | Objection or risk | Confidence | Unresolved gap | Relationship |
|---|---|---|---|---|---|---|---|
| [Agent role] | [substantive finding] | [diagnostic and `file:line`] | [files/boundary] | [strongest objection or risk] | [high/medium/low and why] | [gap or None] | [supports/challenges/unresolved] |

**Synthesis:** [Established/not established, the reconciled causal chain, why
the completion gate passed or failed, and how conflicting evidence was
resolved.]
```

Include every investigator and targeted follow-up once in the map. Keep claims
traceable to evidence. Never include transcripts, tool logs, hidden metadata,
hashes, solution ideas, or implementation steps. Do not collapse substantive
findings into labels such as “clean” or “agreed.”

## Receipt

Return only the runner-provided JSON receipt with `phase: rca`:

- Established: `state: completed`, `result: established`, plus the issue
  identifier and URL.
- One material question remains: `state: needs-input`,
  `result: needs-input`, and exactly one question.
- Cause not established: `state: blocked`, `result: not-established`, and the
  smallest next diagnostic.

Set all Git and pull-request receipt fields to null.

The receipt is the only output returned to the invoking task.
