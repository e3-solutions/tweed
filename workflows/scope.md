# Tweed Solution Scope

Turn the supplied handoff into the smallest implementation-ready solution scope.
For a bug, use only its established RCA; for a feature, use only its intake.
Do not modify repository files, implement the change, create a branch, or
perform any external write other than the final Linear comment.

## Boundaries

- If the handoff contains an existing `## Tweed · Solution Scope`, validate and
  return it before requiring predecessor artifacts.
- Use the kind returned by the context handoff. A bug requires an established
  `## Tweed · Root Cause Analysis`; a feature must not invent or require one.
- Treat the supplied RCA or feature intake as the complete durable request
  contract. Verify material repository claims before relying on them.
- Reuse existing structures, language or framework capabilities, project
  utilities, and installed libraries. Add a dependency, abstraction,
  configuration surface, schema, or migration only when evidence makes it
  necessary.
- Research exact installed versions and repository conventions before proposing
  custom machinery. Use primary sources only when repository evidence is
  insufficient and current dependency behavior matters.
- Separate verified facts and constraints from proposals, assumptions, and
  unresolved decisions.
- Put deployments, credentials, remote configuration, live migrations, and
  production verification in non-blocking post-merge follow-up. The
  implementation contract must be achievable through repository edits and local
  validation.
- Ask the user only when an irreducible product, safety, compatibility, or
  architecture decision prevents a valid scope.

## Scoping workflow

1. Record the exact request, constraints, acceptance clues, and evidence from
   the supplied handoff. For a bug, record the established causal chain and
   responsible boundary. For a feature, characterize current behavior and the
   requested outcome without assuming an implementation. Record the repository
   path, Git `HEAD`, and relevant clean/dirty worktree state. If repository
   evidence materially contradicts the handoff, return `blocked` with the
   smallest re-investigation needed.
2. Spawn exactly three independent read-only agents, without inherited
   conversation:
   - **Repository and reuse:** inventory internal utilities, framework or
     language built-ins, installed libraries and versions, integration points,
     tests, and conventions relevant to the fix.
   - **Product and simplicity:** define the smallest coherent outcome and
     challenge new abstractions, dependencies, configuration, variants, and
     unrelated cleanup.
   - **Robustness and verification:** identify realistic failure,
     compatibility, security, data, concurrency, performance, and operational
     risks; translate supported risks into bounded safeguards and proving
     checks.
3. Give each agent only the issue facts, applicable RCA, repository path, its
   axis, and the read-only evidence standard. Keep initial conclusions blind.
   Require a concise return with recommendation, repository evidence, rejected
   excess, material risks, confidence, and missing information.
4. Synthesize the smallest complete candidate. Every proposed change must map
   to the bug's RCA mechanism, the feature's requested outcome, or an observable
   acceptance criterion.
5. Give only the candidate, constraints, and cited evidence to one fresh
   adversarial reviewer. Require material objections and the minimum correction
   needed; do not request a second general critique.
6. Add one specialist only when a named unresolved risk cannot be decided from
   repository evidence or the baseline agents. Do not add an agent or round
   without a specific unresolved question.
7. Reconcile supported objections. Re-read cited evidence and confirm `HEAD`
   and relevant worktree state before reporting.

## Completion gate

Call the solution scoped only when:

- for a bug, it breaks the established causal chain at the responsible
  boundary; for a feature, it delivers the requested outcome without unrelated
  behavior;
- every included change is necessary and every non-goal is safely unnecessary;
- existing code and installed capabilities are reused where appropriate;
- no custom mechanism duplicates a verified existing capability without a
  material reason;
- changed surfaces and interface effects are explicit;
- realistic failure, compatibility, security, data, and performance effects are
  covered in proportion to evidence;
- acceptance criteria and validation distinguish the fix or delivered feature
  from the prior behavior;
- implementation steps are ordered, locally executable, and independently
  verifiable; and
- no material evidence-backed objection remains unresolved.

If one user decision can close the gap, return `needs-input` with one exact
question, explain its consequence in `summary`, and put concrete options plus a
recommendation in `next_action`. Otherwise return `blocked` and name the
smallest missing investigation. Never fill gaps with speculative architecture.

## Linear comment

Publish one terminal `scoped` comment:

```markdown
## Tweed · Solution Scope

### Outcome
[Smallest complete outcome and how it resolves the bug or delivers the feature.]

### Repository evidence
- [`file:line` or repository result supporting a material boundary]

### Reuse decision
- [Built-in, project utility, or installed library and version]: [reuse choice]
- Custom code required: [narrow uncovered gap, or “None.”]

### Change surface
- [Component/path]: [exact responsibility to change]

### Implementation steps
1. **[Step]**
   - Target: [component/path]
   - Depends on: [step or “None”]
   - Change: [bounded responsibility]
   - Verify: [proving check]

### Non-goals
- [Excluded work and why]

### Acceptance criteria
- [Observable behavior proving the fix]

### Risks and safeguards
- [Evidence-backed risk]: [proportional safeguard]

### Validation
- [Regression, focused, and broader project checks]

### Post-merge follow-up
- [External rollout/live validation, or “None.”]

### Alternatives considered
- [Alternative and evidence-backed rejection]

### Decisions and assumptions
- Decision: [direction] — Basis: [evidence]
- Assumption: [unverified condition, or “None.”]
- Open decision: None

### Repository state
- Repository: [absolute path]
- HEAD: [commit]
- Worktree: [clean or relevant dirty state]

### Debate map
- [Agent axis] — [supports/challenges/unresolved]: [one-line conclusion]
- Synthesis — scoped: [why the gate passed]
```

Include every agent used once. Do not include transcripts, tool logs, hashes,
patches, or implementation work.

## Receipt

Return only the runner-provided JSON receipt with `phase: scope`. A successful
phase uses `state: completed` and `result: scoped`. A clarification uses
`state: needs-input` and `result: needs-input`; other failures use
`state: blocked` and `result: blocked`. Include the issue identifier and URL
when known. Set Git and pull-request fields to null.
