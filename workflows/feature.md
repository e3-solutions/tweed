# Tweed Feature Scope

Turn a feature request into the smallest coherent feature scope and an ordered implementation plan. Do not modify code, implement the feature, or perform external writes.

## Rules

- Inspect the repository before assuming how the feature should work or where it belongs.
- Research language and framework built-ins, existing project utilities, installed dependencies, and their exact versions before proposing custom machinery. Use primary sources such as official documentation or source when repository evidence is insufficient, and cite the relevant capability.
- Keep verified repository facts, requested behavior, assumptions, and proposals distinct.
- Reuse existing product behavior, architecture, libraries, and conventions where appropriate.
- Include a dependency, abstraction, configuration surface, migration, or rollout mechanism only when a concrete requirement or repository constraint needs it.
- When an irreducible product, safety, compatibility, or architecture decision blocks a valid scope, return `Status: blocked` with the exact question. Otherwise state the assumption explicitly.

## Workflow

1. Record the feature request, intended user and outcome, known constraints, repository path, Git `HEAD`, worktree state, and a content fingerprint of files used as evidence. Locate the existing product flow and technical boundaries the feature would extend.
2. Start with independent agents on four axes:
   - **Product behavior:** Define the user-visible outcome, primary journey, expected states, and behavior that is actually required.
   - **Repository and reuse research:** Inventory existing internal utilities, language and framework built-ins, and installed libraries that could satisfy the request. Verify relevant version behavior from repository evidence, official documentation, or source. Identify what can be reused and where custom code remains necessary.
   - **Simplicity and scope:** Find the smallest coherent vertical slice. Challenge speculative flexibility, new abstractions, optional variants, unrelated cleanup, and requirements not supported by the request.
   - **Technical fit and robustness:** Trace integration points and existing conventions. Identify realistic failure states, compatibility constraints, data or API effects, and operational boundaries.
3. Synthesize a provisional feature scope and ordered implementation approach grounded in repository evidence.
4. As the baseline adversarial check, give the provisional scope, not raw transcripts, back to all four agents. Require each to falsify it against its objective and return only material objections and the minimum correction needed.
5. Add an independent specialist only for a material open question involving performance, security or privacy, permissions, accessibility, data integrity, concurrency, migration, rollout, observability, or testability.
6. Reconcile supported objections. Continue targeted debate while a concrete agent task or repository check can resolve a material gap or contradiction.
7. Re-read cited files and conventions, confirm that `HEAD`, relevant worktree state, and evidence-file fingerprints have not changed, then verify the final scope and implementation steps against the completion gate. If relevant state changed, return `Status: blocked` instead of reporting a stale plan.

After the baseline challenge, do not add an agent or round without a specific unresolved question. A smaller scope must still produce a coherent user outcome; a more robust scope must address a realistic risk in this system.

## Completion gate

Call the feature scoped only when:

- the intended user, outcome, and observable behavior are explicit;
- the proposal fits verified repository boundaries and conventions;
- existing built-ins, project utilities, and installed libraries were researched and reused wherever they satisfy the requirement without a material tradeoff;
- its material repository claims are supported by auditable file references;
- the scope is the smallest coherent vertical slice, with defensible non-goals;
- interfaces, state changes, failure behavior, and compatibility effects are explicit where applicable;
- security, performance, migration, rollout, and operational work are included only when materially required;
- acceptance criteria distinguish completion from partial implementation;
- implementation steps are ordered, independently verifiable, and sufficient to deliver the scope; and
- no material evidence-backed objection remains unresolved.

If the gate fails, return `Status: blocked`, name the narrow blocker or user decision needed, and do not fill the gap with invented requirements.

## Output

```markdown
Status: [scoped | blocked]

# Feature scope

[Smallest coherent feature definition.]

## Outcome

- User: [who benefits]
- Result: [observable outcome]

## User experience

1. [Primary journey or state transition]

## Proposed solution

[Repository-grounded technical approach and why it fits.]

## Repository evidence

- [File:line or repository result supporting a material boundary or convention]

## Reuse research

- [Built-in, project utility, or installed library and exact version]: [capability, evidence/source, and reuse decision]
- Custom code still required: [narrow gap not covered by existing capabilities]

## Repository state

- Repository: [absolute repository path]
- HEAD: [Git commit, or "not a Git repository"]
- Relevant worktree: [clean, or paths/status relevant to the scope]
- Evidence snapshot: [one `path → SHA-256` entry for every existing cited file, planned write target, and material interface or test; use `path → ABSENT` for a planned new file]

## Change surface

- [Component, interface, data, or configuration responsibility]

## Implementation steps

1. **[Step name]**
   - Target: [repository component or boundary]
   - Depends on: [earlier step or "None"]
   - Responsibility: [concrete change this step would make]
   - Verify: [check that proves this step complete]

## Non-goals

- [Explicitly excluded work and why]

## Acceptance criteria

- [Observable product or system behavior]

## Risks and safeguards

- [Evidence-backed risk and proportional safeguard]

## Validation and rollout

- [Test, diagnostic, migration, or rollout check when applicable]

## Alternatives considered

- [Alternative and evidence-backed reason it was rejected or partially used]

## Decisions and assumptions

- Decision: [selected direction] — Basis: [request, repository evidence, or resolved objection]
- Assumption (unverified): [condition the scope relies on]
- Open decision: [required user choice, or "None"]

## Debate map

Feature request
├─ [Agent axis] — [supports/challenges/unresolved]: [one-line conclusion]
├─ [Agent axis] — [supports/challenges/unresolved]: [one-line conclusion]
└─ Synthesis — [scoped/blocked]: [why the gate passed or failed]
```

Include every agent actually used once in the map. Do not include transcripts, tool logs, patches, implementation work, or unrelated follow-ups.
