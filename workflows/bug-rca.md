# Tweed Bug RCA

Investigate the bug from the supplied handoff and publish one evidence-backed
root cause analysis as its first Tweed comment. Keep all repository
investigation in isolated subagents so the invoking task receives only the
bounded receipt.

## Boundaries

- The input must identify an existing Linear bug issue. If it does not, return
  `needs-input`; never create or guess an issue. If the issue is a feature,
  return `blocked` because features proceed directly to scope.
- Reuse a supplied existing RCA and stop. Otherwise use only the supplied
  intake.
- Do not change the issue title or description, modify project files, install
  dependencies, add helper code, create a branch, propose a fix, or implement
  anything.
- Use existing repository tools, tests, history, logs, and configuration.
- Treat the issue report as a symptom, not as a proven explanation.
- Prefer runtime, test, repository, configuration, and history evidence over
  agent opinion.
- Inspect available evidence before asking the user. Ask only when one material
  fact cannot be discovered from the repository or supplied intake.

## Investigation workflow

1. Read the supplied intake and record the exact reported and expected behavior,
   impact, acceptance clues, affected surface, reproduction details,
   environment, constraints, and supplied evidence. Do not silently fill gaps.
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

Direct evidence can include a reproduction, execution trace, failing test,
focused diagnostic, logs, telemetry, or configuration/history records. A
plausible theory, code smell, or investigator consensus is not enough.

If one user answer could close the evidence gap, return `needs-input` with one
concise question. Use `summary` to explain why it matters and `next_action` for
concrete options or an evidence-backed recommendation. Do not write a Linear
comment yet. If repository work cannot establish the cause and no single answer
will do so, report `not-established` and name the smallest next diagnostic.

## First Tweed comment

For terminal `established` or `not-established` results, add exactly one comment
in this form:

```markdown
## Tweed · Root Cause Analysis

**Status:** Established | Not established

### Root cause
[Precise causal statement, or “Root cause not established.”]

### Problem definition
[Observed and expected behavior, impact, constraints, acceptance clues,
affected surface, and triggering conditions now known.]

### Failure chain
1. [Trigger]
2. [Responsible boundary and mechanism]
3. [Observed failure]

### Evidence
- [Diagnostic, runtime, history, configuration, or `file:line` evidence]

### Alternative checked
- [Strongest credible alternative and why it does or does not fit]

### Remaining uncertainty
[Material unknowns, or “None.”]

### Repository state
- Repository: [absolute path]
- HEAD: [commit, or “not a Git repository”]
- Worktree: [clean or relevant dirty/untracked state]

### Investigation map
- [Agent role] — [supports/challenges/unresolved]: [one-line conclusion]
- Synthesis — [established/not established]: [why the gate passed or failed]
```

Include every investigator and targeted follow-up once in the map. Keep claims
traceable to evidence. Never include transcripts, tool logs, hidden metadata,
hashes, solution ideas, or implementation steps.

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
