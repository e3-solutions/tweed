# Tweed Solution Scope

Turn the supplied Linear request into the smallest implementation-ready solution
scope. For a bug, start from its established RCA. For a feature, start from the
requested outcome and verified repository behavior. Use Linear MCP yourself to
read the issue and applicable Tweed comments, check for an existing scope, and
publish the final scope. Children must not use Linear. Do not modify repository
files, implement the change, create a branch, or perform any external write
other than the final Linear comment.

## Durable phase boundary

- This is a fresh phase coordinator. Its only request-specific input is the
  Linear issue identifier. Read the issue description and all completed prior
  Tweed comments from Linear. Do not expect or accept inherited coordinator or
  subagent context, a prior report injected into the prompt, hidden files, or
  local phase state.
- The issue description and completed Tweed comments are the complete durable
  handoff. The compact JSON receipt is control-plane data only. Resuming this
  same coordinator after `needs-input` is the sole within-phase exception.
- Before returning `completed`, publish and re-read the scope comment. It must
  be sufficient for a fresh implementation coordinator that knows only the
  issue identifier. If any material basis, file responsibility, decision,
  ordering constraint, risk, or proving check remains only in this
  coordinator's context, do not complete the phase.

## Boundaries

- Determine whether the issue is a bug or feature from `**Kind:**` in its
  description, falling back to an unambiguous existing label. A bug requires an
  established `## Tweed · Root Cause Analysis`
  comment. A feature must not invent or require an RCA. If the kind is ambiguous
  or a bug lacks established RCA, return `needs-input` or `blocked`.
- Treat the issue description and, for bugs, RCA as the durable request
  contract. Require applicable prior comments to satisfy their self-contained
  handoff schemas, and verify material repository claims before relying on
  them. Return `blocked` instead of reconstructing a missing prior report from
  any non-Linear context.
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

1. Record the exact request, constraints, acceptance clues, and supplied
   evidence. For a bug, record the established causal chain and responsible
   boundary. For a feature, characterize current behavior and the requested
   outcome without assuming an implementation. Record the repository path, Git
   `HEAD`, and relevant clean/dirty worktree state. If repository evidence
   materially contradicts the handoff, return `blocked` with the smallest
   re-investigation needed.
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
   Consolidate every material conclusion in the final debate map with its
   evidence, affected files or boundaries, objection or risk, confidence, and
   unresolved gap. Never paste raw returns, transcripts, or tool logs.
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

The Linear comment itself must satisfy this gate. It must tie the outcome to
the established RCA or feature request, provide repository evidence, assign an
exact responsibility to every file or boundary in the change surface, record
reuse choices, order dependent implementation steps, and preserve acceptance,
validation, risks, safeguards, non-goals, alternatives, decisions,
assumptions, and substantive debate findings. Coordinator knowledge that is
not present in the verified comment does not count.

If one user decision can close the gap, return `needs-input` with one exact
question, explain its consequence in `summary`, and put concrete options plus a
recommendation in `next_action`. Otherwise return `blocked` and name the
smallest missing investigation. Never fill gaps with speculative architecture.

## Linear comment

If a comment already begins with `## Tweed · Solution Scope`, validate it is
complete under the current gate and return it instead of duplicating the phase.
If it is incomplete, return `blocked` and identify the missing durable handoff
facts. Otherwise publish one terminal `scoped` comment:

```markdown
## Tweed · Solution Scope

### Handoff basis
- Request outcome: [exact issue outcome this scope delivers]
- RCA link (bug): [established causal chain and responsible boundary, or “Not applicable — feature”]
- Constraints carried forward: [material issue/RCA constraints]

### Outcome
[Smallest complete outcome and how it resolves the bug or delivers the feature.]

### Repository evidence
- [`file:line` or repository result supporting a material boundary]

### Reuse decision
- [Built-in, project utility, or installed library and version]: [reuse choice]
- Custom code required: [narrow uncovered gap, or “None.”]

### Change surface
| File or boundary | Current evidence | Exact responsibility | Interface/caller effect |
|---|---|---|---|
| [`path` or boundary] | [`file:line` or repository result] | [bounded change] | [consumer effect or None] |

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
| Risk | Evidence and affected boundary | Safeguard | Proving check |
|---|---|---|---|
| [Evidence-backed risk] | [repository fact and surface] | [proportional safeguard] | [validation] |

### Validation
- [Regression, focused, and broader project checks]

### Post-merge follow-up
- [External rollout/live validation, or “None.”]

### Alternatives considered
| Alternative | Evidence | Decision and reason |
|---|---|---|
| [Alternative] | [repository or dependency evidence] | [rejected/partially reused and why] |

### Decisions and assumptions
- Decision: [direction] — Basis: [evidence]
- Assumption: [unverified condition, or “None.”]
- Open decision: None

### Repository state
- Repository: [absolute path]
- HEAD: [commit]
- Worktree: [clean or relevant dirty state]

### Debate map
| Axis/role | Material conclusion | Evidence | Affected surface | Objection or risk | Confidence | Unresolved gap | Relationship |
|---|---|---|---|---|---|---|---|
| [Agent axis] | [substantive finding] | [`file:line`, version, or diagnostic] | [files/boundary] | [challenge or risk] | [high/medium/low and why] | [gap or None] | [supports/challenges/resolved] |

**Adversarial review:** [material objection, evidence, and minimum correction,
or “No material objection after evidence review.”]

**Synthesis:** [Why this is the smallest complete scope, how supported
objections were resolved, and why the completion gate passed.]
```

Include every agent used once. Do not include transcripts, tool logs, hashes,
patches, or implementation work. Do not replace evidence-bearing findings with
generic statements such as “approved” or “clean.”

## Receipt

Return only the runner-provided JSON receipt with `phase: scope`. A successful
phase uses `state: completed` and `result: scoped`. A clarification uses
`state: needs-input` and `result: needs-input`; other failures use
`state: blocked` and `result: blocked`. Include the issue identifier and URL
when known. Set Git and pull-request fields to null.
