# Tweed Scope

Turn the supplied frozen artifact packet into an implementation-ready solution scope. Verify each referenced artifact hash before use and open only the request and established RCA artifacts relevant to this phase; do not load the complete Linear description or prior transcripts. For a `problem`, scope from its established RCA. For a `feature`, scope directly from its original request. Identify exactly what should change and why, but do not modify code, implement the change, or perform external writes.

## Rules

- Verify the issue is at stage `needs-scope`. For a `problem`, proceed only from an established root cause with concrete evidence. For a `feature`, proceed from the recorded request and verified repository behavior. Otherwise return `Status: blocked` and do not design a solution.
- Do not modify project files, use Linear tools, or cause external side effects while scoping or clarifying.
- Reuse existing structures, libraries, and conventions. Add a dependency, abstraction, configuration surface, or migration only when evidence makes it necessary.
- Research language and framework built-ins, existing project utilities, installed dependencies, and their exact versions before proposing custom machinery. Use primary sources such as official documentation or source when repository evidence is insufficient.
- Separate verified facts and constraints from proposals and unresolved decisions.
- Inspect the repository and completed RCA before asking the user. When an irreducible product, safety, compatibility, or architecture choice blocks a valid scope, return `Status: needs-input` with one exact question, its consequences, concrete options, and an evidence-backed recommendation when possible.
- After receiving a clarification answer, normalize it as a decision, reconcile it with repository evidence, and continue the same scope. Do not repeat an answered question.
- Every implementation step must be executable through repository edits and local validation inside the future runner-owned worktree. Put deployments, credential creation, remote configuration, live migrations, production/staging exercises, and other external actions in an explicitly non-blocking post-merge follow-up; never make them an implementation dependency or completion criterion.
- Compute every evidence SHA-256 from the final file bytes, preserve all 64 lowercase hexadecimal characters, and verify the completed snapshot before returning. Never transcribe or abbreviate a digest manually.

## Workflow

1. Freeze the supplied request and, for a problem, its verified root cause. Record the repository path, Git `HEAD`, worktree state, evidence snapshot, constraints, and supporting evidence. Verify that the reported repository state still matches the current state. If relevant state changed, return `Status: blocked` instead of scoping stale input.
2. Start exactly three independent agents:
   - **Repository and reuse:** Inventory internal utilities, language and framework built-ins, installed libraries, integration points, and exact-version behavior needed by the request.
   - **Product and simplicity:** Define the smallest coherent user-visible outcome and challenge new abstractions, dependencies, configuration, variants, and unrelated cleanup.
   - **Robustness and verification:** Find realistic failure, compatibility, security, data, concurrency, performance, and operational risks; turn them into bounded safeguards and proving checks.
3. If an initial agent is interrupted or fails, replace it once with the same frozen input. If the replacement fails, return `Status: blocked` rather than waiting indefinitely.
4. Synthesize the smallest complete candidate from their bounded packets.
5. Give only that candidate and its evidence to one fresh adversarial reviewer. Require material objections and the minimum correction needed; do not start a second general critique round.
6. Add one specialist only when a named unresolved risk cannot be adjudicated from repository evidence or the three baseline packets.
7. Reconcile supported objections, ask the user only when investigation cannot resolve a material decision, then re-read cited evidence and confirm `HEAD`, relevant worktree state, and evidence-file fingerprints have not changed.

Do not add an agent or round without a specific unresolved question. Do not prefer a proposal merely because it changes fewer lines, and do not add safeguards for hypothetical risks unsupported by this system.

## Completion gate

Call the solution scoped only when:

- it addresses the requested outcome and, for a problem, the verified mechanism at the responsible boundary;
- every included change is necessary and every non-goal is safely unnecessary;
- realistic failure modes, compatibility constraints, and performance effects are covered;
- existing code and dependencies are reused where appropriate;
- no custom mechanism duplicates a verified built-in, project utility, or installed-library capability without a material reason;
- changed surfaces and interface effects are explicit;
- acceptance criteria and verification distinguish the real fix from the original failure; and
- implementation steps are ordered, independently verifiable, and sufficient to deliver the scope; and
- implementation steps require only repository edits and local checks, with external rollout or runtime validation clearly separated as post-merge follow-up; and
- every evidence snapshot digest is a verified 64-character SHA-256 of the cited final file bytes, or `ABSENT` for a path that is confirmed absent; and
- no material evidence-backed objection remains unresolved.

If the gate fails because a user decision can resolve it, return `Status: needs-input`. Return `Status: blocked` for a stale or invalid RCA, an inaccessible Linear handoff, or another blocker that clarification cannot resolve. Do not fill gaps with speculative architecture.

## Clarification output

When user input is required, return only:

```markdown
Status: needs-input

# Clarification needed

## Question

[One material question.]

## Why this matters

[How the answer changes the solution contract.]

## Options

- [Option and its consequence]

## Recommendation

[Evidence-backed recommendation, or "None yet."]
```

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

## Post-merge follow-up

- [External rollout, provisioning, or live validation action that is not part of implementation, or "None"]

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

## Structured return

Return the result through the runner-provided JSON schema with `status`, a bounded `summary`, optional structured `question`, and the complete report in `report_markdown`. The report must begin with the matching `Status:` line. Never use Linear tools; the runner alone persists a completed phase.
