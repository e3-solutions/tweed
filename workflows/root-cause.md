# Tweed Root Cause

Identify the problem and its evidence-backed root cause. Do not propose, scope, or implement a solution. Keep subagent returns short so the main context stays focused.

## Rules

- Do not modify project files, write to Linear, or cause external side effects.
- Use existing project tools and tests. Add no dependencies or helper code.
- Treat the user's report as a symptom, not a proven explanation.
- Prefer runtime, test, repository, and history evidence over agent opinion.
- When missing information blocks useful investigation, return `Status: not-established` with the smallest blocking question.

## Workflow

1. Record the exact report, repository path, expected behavior when known, constraints, and supplied evidence. Record Git `HEAD`, whether the worktree is dirty, and a content fingerprint of files used as evidence. Treat a dirty worktree as live state, not as evidence from `HEAD`.
2. Spawn independent investigators with distinct jobs appropriate to the problem. Cover reproduction or symptom characterization, execution tracing, and falsification of competing explanations when applicable. Keep their initial conclusions blind.
3. Run independent work concurrently when slots permit. Otherwise run it in waves without revealing earlier conclusions.
4. Require concise, evidence-backed returns containing only material claims, confidence, and missing evidence. Retain each agent's role, one-line conclusion, and relationship to the final diagnosis: `supports`, `challenges`, or `unresolved`.
5. Identify the best-supported causal chain and its strongest credible alternative.
6. While the completion gate is not satisfied and a concrete next step can produce new evidence, delegate the needed follow-up, falsifier, or domain specialist and reconcile the result. Share relevant claims and evidence, not raw transcripts.
7. Immediately before reporting, re-read cited code, confirm the evidence-file fingerprint has not changed, and rerun the smallest confirming diagnostic when feasible. If relevant state changed, reconcile the investigation against the new state before reporting.

Do not add agents or rounds that cannot resolve a specific evidence gap or contradiction. Disclose when findings come from a dirty worktree.

## Completion gate

Call the root cause established only when the evidence identifies:

- the triggering condition;
- the responsible code, configuration, data, dependency, or environment boundary;
- the mechanism connecting the trigger to the observed failure; and
- why the strongest credible alternative does not fit the evidence.

The failure and causal chain must have direct evidence such as reproduction, execution tracing, a failing test, logs, telemetry, or configuration/history records. If the gate does not pass, say `Root cause not established` and report the smallest next diagnostic or one blocking question. Never promote a plausible hypothesis to a fact.

## Output

```markdown
Status: [established | not-established]

# Root cause

[Precise causal statement, or "Root cause not established."]

## Problem definition

[Observed behavior, expected behavior, and triggering conditions now known.]

## Failure chain

1. [Trigger]
2. [Mechanism]
3. [Observed failure]

## Evidence

- [Runtime result, command result, or file:line reference]

## Alternative checked

- [Strongest alternative and why it does or does not fit]

## Remaining uncertainty

[Material unknowns, or "None."]

## Repository state

- Repository: [absolute repository path]
- HEAD: [Git commit, or "not a Git repository"]
- Worktree: [clean/dirty, including relevant untracked state]
- Evidence snapshot: [one `path → SHA-256` entry for every cited evidence file]

## Investigation map

Problem
├─ [Agent role] — [supports/challenges/unresolved]: [one-line conclusion]
├─ [Agent role] — [supports/challenges/unresolved]: [one-line conclusion]
└─ Synthesis — [established/not established]: [why the gate passed or failed]
```

Include every agent actually used, including targeted follow-ups, once in the map. Do not include transcripts, tool logs, solution ideas, or implementation steps.
