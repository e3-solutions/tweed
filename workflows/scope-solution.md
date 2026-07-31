# Tweed Solution Scope

Turn an established root cause into an implementation-ready solution scope. Identify exactly what should be changed and why, but do not modify code, implement the change, or perform external writes.

## Rules

- Proceed only from an established root cause with concrete evidence. Otherwise return `Status: blocked` and do not design a solution.
- Do not modify project files, write to Linear, or cause external side effects.
- Reuse existing structures, libraries, and conventions. Add a dependency, abstraction, configuration surface, or migration only when evidence makes it necessary.
- Research language and framework built-ins, existing project utilities, installed dependencies, and their exact versions before proposing custom machinery. Use primary sources such as official documentation or source when repository evidence is insufficient.
- Separate verified facts and constraints from proposals and unresolved decisions.
- When an irreducible product, safety, compatibility, or architecture choice blocks a valid scope, return `Status: blocked` with the exact decision needed.

## Workflow

1. Freeze the verified root cause, repository path, Git `HEAD`, worktree state, evidence snapshot, constraints, and supporting evidence. Verify that the reported repository state still matches the current state. If relevant state changed, return `Status: blocked` instead of scoping a stale diagnosis.
2. Start with independent agents on four axes:
   - **Repository and reuse research:** Inventory internal utilities, language and framework built-ins, and installed libraries that could break the verified causal chain. Verify exact-version behavior from repository evidence, official documentation, or source, and identify the narrow gap custom code must fill.
   - **Simplicity:** Find the smallest causal change and challenge new abstractions, dependencies, configuration, and unrelated cleanup.
   - **Robustness and stability:** Find realistic failure modes, edge cases, compatibility hazards, partial failures, and rollback needs. Challenge a patch that fixes only the example.
   - **Performance:** Inspect hot paths, latency, resource use, scaling behavior, and the overhead of proposed safeguards.
3. Synthesize the smallest candidate that breaks the verified causal chain at the responsible boundary.
4. As the baseline adversarial check, give that candidate, not raw transcripts, back to the four axis agents. Require each to try to falsify it against its objective and return only evidence-backed objections and the minimum correction needed.
5. Add an independent specialist only for a material open question in feasibility, testability, integration or compatibility, security or privacy, data integrity, concurrency, migration, or operations.
6. Reconcile supported objections. Continue targeted debate while a concrete agent task or repository check can resolve a material gap or contradiction.
7. Re-read cited files and conventions, confirm that `HEAD`, relevant worktree state, and evidence-file fingerprints have not changed, then verify the final scope against the completion gate. If relevant state changed, return `Status: blocked` instead of reporting a stale plan.

After the baseline challenge, do not add an agent or round without a specific unresolved question. Do not prefer a proposal merely because it changes fewer lines, and do not add safeguards for hypothetical risks unsupported by this system.

## Completion gate

Call the solution scoped only when:

- it addresses the verified mechanism at the responsible boundary;
- every included change is necessary and every non-goal is safely unnecessary;
- realistic failure modes, compatibility constraints, and performance effects are covered;
- existing code and dependencies are reused where appropriate;
- no custom mechanism duplicates a verified built-in, project utility, or installed-library capability without a material reason;
- changed surfaces and interface effects are explicit;
- acceptance criteria and verification distinguish the real fix from the original failure; and
- implementation steps are ordered, independently verifiable, and sufficient to deliver the scope; and
- no material evidence-backed objection remains unresolved.

If the gate fails, return `Status: blocked`, name the narrow blocker, and do not fill the gap with speculative architecture.

## Output

```markdown
Status: [scoped | blocked]

# Solution scope

[Smallest complete implementation scope.]

## Why this scope

[How it breaks the verified causal chain without unnecessary machinery.]

## Repository evidence

- [File:line or repository result supporting a material boundary or convention]

## Reuse research

- [Built-in, project utility, or installed library and exact version]: [capability, evidence/source, and reuse decision]
- Custom code still required: [narrow gap not covered by existing capabilities]

## Change surface

- [Component and exact responsibility to change]

## Repository state

- Repository: [absolute repository path]
- HEAD: [Git commit, or "not a Git repository"]
- Relevant worktree: [clean, or paths/status relevant to the scope]
- Evidence snapshot: [one `path → SHA-256` entry for every existing cited file, planned write target, and material interface or test; use `path → ABSENT` for a planned new file]

## Implementation steps

1. **[Step name]**
   - Target: [repository component or boundary]
   - Depends on: [earlier step or "None"]
   - Responsibility: [concrete change this step would make]
   - Verify: [check that proves this step complete]

## Non-goals

- [Explicitly excluded work and why]

## Acceptance criteria

- [Observable behavior proving the fix]

## Risks and safeguards

- [Evidence-backed risk and proportional safeguard]

## Validation

- [Test or diagnostic that distinguishes fixed from broken]

## Alternatives considered

- [Alternative and evidence-backed reason it was rejected or partially used]

## Decisions and assumptions

- Decision: [selected direction] — Basis: [RCA evidence or resolved objection]
- Assumption (unverified): [condition the scope relies on]
- Open decision: [required user choice, or "None"]

## Debate map

Verified RCA
├─ [Agent axis] — [supports/challenges/unresolved]: [one-line conclusion]
├─ [Agent axis] — [supports/challenges/unresolved]: [one-line conclusion]
└─ Synthesis — [scoped/blocked]: [why the gate passed or failed]
```

Include every agent actually used once in the map. Do not include transcripts, tool logs, patches, implementation work, or unrelated follow-ups.
