# Bonaparte Bug RCA

Investigate the supplied bug handoff and publish one evidence-backed root cause
analysis. The runner has selected the issue intake or latest existing RCA.
Use Linear only to publish and verify the final RCA comment.

## Boundaries

- The input must identify an existing Linear bug issue. If it does not, return
  `needs-input`; never create or guess an issue. If the issue is a feature,
  return `blocked` because features proceed directly to scope.
- Do not change the issue title or description, modify project files, install
  dependencies, add helper code, create a branch, propose a fix, or implement
  anything. All diagnostics and evidence access must be read-only; do not mutate
  runtime data, infrastructure, dependencies, providers, or other external state.
- Use relevant available repository, runtime, data, infrastructure, dependency,
  and external-service evidence. Start from the affected causal path; do not run
  broad source or telemetry scans without a material question.
- Treat the issue report as a symptom, not as a proven explanation.
- Prefer runtime, test, repository, configuration, and history evidence over
  agent opinion.

## Investigation workflow

1. Read the supplied intake and record the exact reported behavior, expected
   behavior when known, affected surface, reproduction details, environment,
   constraints, and supplied evidence. Identify the exact affected artifact,
   incident window, and correlation identifiers when applicable. Mark unknowns;
   do not silently fill gaps or attach evidence from a merely similar artifact.
2. Record the absolute repository path, Git `HEAD`, and whether the worktree is
   clean or dirty. Treat dirty and untracked files as live state rather than as
   evidence from `HEAD`, and disclose when they affect the finding.
3. Trace only boundaries implicated by the reported path. For lifecycle-based
   integrations such as subscriptions, leases, tokens, or webhooks, follow
   create, persist, renew or reconnect, expire or revoke, and deliver. Correlate
   local and dependency/provider telemetry or status by timestamp or request ID.
4. Build the phase coverage map from the causal path. Put exact artifact and
   timeline facts, boundary behavior, competing explanations, and missing proof
   on the frontier. Form a small set of falsifiable hypotheses only when they are
   materially distinct; test the highest-information hypothesis first.
5. Use zero to three read-only investigators total for the phase, including any
   follow-up. Combine related work for a narrow path. Delegate only distinct
   frontier assignments about artifact/timeline, execution or runtime boundaries,
   or falsifying the leading explanation.
6. Brief each child under the coordinator's delegation policy. Additionally name
   the diagnostic and what would support or falsify the claim. Keep initial
   conclusions blind when that reduces anchoring.
7. Require each return to be at most 300 words and contain only:

   ```text
   Conclusion: precise claim
   Evidence: diagnostic result and source/location (`file:line` when applicable)
   Confidence: high | medium | low, with reason
   Missing: missing evidence or none
   Relationship: supports | challenges | unresolved
   ```

8. Reconcile the results and update the coverage map. Identify the best-supported
   causal chain, strongest credible alternative, contradictions, and evidence
   still missing from the completion gate. Route each material gap to an available
   diagnostic, one user-only fact, or a specifically unavailable source. An
   unattempted query is not unavailable evidence.
9. Within the same zero-to-three total, use a targeted follow-up investigator
   only when a concrete diagnostic can resolve a named gap or contradiction.
   Share relevant claims and evidence, not raw transcripts. Do not add agents or
   rounds that cannot change the conclusion.
10. Immediately before reporting, re-read every cited source and rerun
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

For a time-dependent incident, identify the artifact and align the cause with its
window. Static evidence proves susceptibility, not the incident; require a
reproduction or correlated runtime evidence at the failing boundary. Attempt the
smallest conclusion-changing diagnostics that can be completed without an
unbounded wait; otherwise name the smallest unavailable or next diagnostic.

Direct evidence can include a reproduction, execution trace, failing test,
focused diagnostic, logs, telemetry, or configuration/history records. A
plausible theory, code smell, or investigator consensus is not enough.

When the gate does not pass:

- Run any remaining bounded, read-only diagnostic that can change the conclusion.
- If one user answer can close the gap, return `needs-input`; explain its effect in
  `summary`, mirror useful detail in `next_action`, and do not write Linear yet.
- Otherwise return `blocked` with `result: not-established` and name the smallest
  unavailable or next diagnostic.

## First Bonaparte comment

After `needs-input` has been ruled out, keep one durable RCA slot in Linear. If
the gate passes, its status is `Established`. If the gate does not pass and no
RCA comment exists, create that slot with status `Not established`; do not add
another comment or overwrite an existing RCA with a second inconclusive attempt.

Handle the selected RCA deterministically:

- No existing RCA: add one comment in the schema below.
- Existing RCA: treat it as a hypothesis and recheck it against the original
  intake and current gate. Reuse it unchanged if it passes. Otherwise investigate
  its gaps and update `existing_comment_id` only after a fresh terminal result
  passes. If the ID is unavailable, return `blocked`. Never append a competing RCA.

After adding or updating, re-read the comment. Return `completed` only when the
selected comment matches this schema and satisfies the completion gate.

```markdown
## Bonaparte · Root Cause Analysis

**Status:** Established | Not established

### Root cause
[Precise causal statement, or “Root cause not established.”]

### Incident
- Observed: [behavior and affected surface]
- Expected: [expected behavior]
- Trigger/window: [trigger, artifact, environment, and incident window]

### Causal chain
1. [Trigger]
2. [Responsible boundary and mechanism]
3. [Observed failure]

### Evidence
| Claim | Evidence | What it proves |
|---|---|---|
| [causal claim] | [source + time/ID, diagnostic, or `file:line`] | [direct implication] |

### Alternatives checked
| Alternative | Decisive check | Result |
|---|---|---|
| [strongest alternative] | [check] | [rejected/unresolved — reason] |

### Remaining uncertainty
[Material unknowns, or “None.”]

### Repository state
- Repository: [absolute path]
- HEAD: [commit, or “not a Git repository”]
- Worktree: [clean or relevant dirty/untracked state]
```

Keep each material claim traceable to evidence. Never include agent identities,
transcripts, tool logs, hidden metadata, unrelated hash data, solution ideas, or
implementation steps.

## Receipt

Return only the runner-provided JSON receipt with `phase: rca`:

- Established: `state: completed`, `result: established`, plus the issue
  identifier and URL.
- One material question remains: `state: needs-input`,
  `result: needs-input`, and exactly one question.
- Cause not established: `state: blocked`, `result: not-established`, and the
  smallest next diagnostic. Set `remote_state_changed` to true only when this
  turn created the first `Not established` comment; otherwise set it to false.

Set all Git and pull-request receipt fields to null.

The receipt is the only output returned to the invoking task.
