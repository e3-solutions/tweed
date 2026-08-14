# Bonaparte Solution Scope

Turn the supplied Linear request into the smallest implementation-ready solution
scope. For a bug, start from its established RCA. For a feature, start from the
requested outcome and verified repository behavior. The runner supplies only
the selected intake, latest RCA, or latest existing scope needed for this phase.
Use Linear only to publish and verify the final scope. Children must not use
Linear. Do not modify repository files, implement the change, create a branch,
or perform any other external write.

## Boundaries

- Use the supplied issue kind. A bug requires an established
  `## Bonaparte · Root Cause Analysis` handoff. A feature receives its intake and
  must not invent or require an RCA. If the kind is missing or a bug lacks its
  RCA handoff, return `needs-input` or `blocked`.
- Treat the supplied feature intake or bug RCA as the durable request contract.
  Verify material repository claims before relying on them.
- Reuse existing structures, language or framework capabilities, project
  utilities, and installed libraries. Add a dependency, abstraction,
  configuration surface, schema, or migration only when evidence makes it
  necessary.
- Research exact installed versions and repository conventions before proposing
  custom machinery. Use primary sources only when repository evidence is
  insufficient and current dependency behavior matters.
- Separate verified facts and constraints from proposals, assumptions, and
  unresolved decisions.
- Resolve any uncertainty that can change an acceptance criterion's feasibility
  or design with direct evidence before scope completes. Do not waive it as
  safe degradation or close it with an assumption or a synthetic fixture based
  only on the proposed behavior. A later conformance uncertainty may remain
  only as an explicit proof obligation, not a verified fact.
- Keep deployments, credentials, remote configuration, live migrations, and
  production verification out of implementation. For each state-changing
  external prerequisite, record safe ordering, verification, and rollback; do
  not call it non-blocking when safe operation depends on it.
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
2. Use zero to three read-only agents only for distinct decisions; the
   coordinator may combine applicable axes for a narrow change:
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
3. Require a concise recommendation with source locations, rejected excess,
   material risks, confidence, and missing information. Keep conclusions blind
   when that reduces anchoring.
4. Synthesize the smallest complete candidate. Every proposed change must map
   to the bug's RCA mechanism, the feature's requested outcome, or an observable
   acceptance criterion.
5. Classify each acceptance criterion's proving boundary and record its smallest
   decisive proof and owner. Simple local logic may use a coordinator-owned
   deterministic check. A changed external/native protocol, process lifecycle,
   persistence/concurrency invariant, or producer-consumer boundary requires
   fresh read-only verification in both implementation and review, using,
   respectively: the installed primary contract plus
   captured/live behavior; injected exit/error/interruption with resource
   cleanup proof; interruption/retry/competing-access proof; or an end-to-end
   consumer canary. Combine compatible obligations under one verifier and do
   not verify boundaries the change does not touch.
6. If the request cannot fit one coherent implementation packet, propose ordered
   valuable packets and ask which comes first. Do not publish an omnibus scope.
7. Apply adversarial checks directly, delegating to one fresh reviewer only for
   a named objection or unresolved decision. Require only material objections
   and the minimum correction.
8. Add one specialist only when a named unresolved risk cannot be decided from
   repository evidence or the coordinator's current analysis. Do not add an
   agent or round without a specific unresolved question.
9. Reconcile supported objections. Re-read cited evidence and confirm `HEAD`
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
- every acceptance criterion names its trigger, observable outcome, and smallest
  proving check; include a before/after bug regression when feasible and broader
  suites only when justified;
- every acceptance criterion has a classified proof obligation and owner, and
  no design-affecting uncertainty remains unresolved;
- implementation steps are ordered, locally executable, and independently
  verifiable; and
- no material evidence-backed objection remains unresolved.

If one user decision can close the gap, return `needs-input` with one exact
question containing supported options and a recommendation for confirmation or
correction. Explain its consequence in `summary`. Otherwise return `blocked`
with the smallest missing investigation; never invent architecture.

## Linear comment

If an `existing` solution scope was supplied, validate it under the current
gate. Treat it as the immediately preceding legacy schema only when it contains
the outcome, repository evidence, reuse decision, change surface,
implementation steps, non-goals, acceptance criteria, risks and safeguards,
validation, decisions and assumptions, and repository state, but lacks
`### Proof obligations`. For that case only, classify the carried acceptance
criteria under step 5 without redesigning the accepted scope, revalidate
material repository facts, and publish one refreshed current-schema scope. The
missing table alone is not a blocker; any missing contract fact, design change,
or unresolved design-affecting uncertainty is. A complete current scope may be
returned only after validation; any other incomplete scope returns `blocked`.
For a new or upgraded scope, publish one terminal `scoped` comment:

After writing, re-read the comment and return `completed` only if it matches
this schema and contains the evidence required by the completion gate.

```markdown
## Bonaparte · Solution Scope

### Handoff basis
- RCA basis: [causal chain and responsible boundary, or “Not applicable — feature”]
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

### Proof obligations
| Acceptance criterion | Boundary type | Direct evidence required | Verification owner |
|---|---|---|---|
| [criterion] | [local logic/protocol/process/persistence/concurrency/producer-consumer] | [smallest decisive check] | [coordinator or fresh read-only verifier] |

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
| Axis/role | Material conclusion | Evidence | Affected surface | Confidence | Relationship |
|---|---|---|---|---|---|
| [Agent axis] | [substantive finding] | [`file:line`, version, or diagnostic] | [files/boundary] | [high/medium/low and why] | [supports/challenges/resolved] |

**Adversarial review:** [Material objection, evidence, and minimum correction,
or “No material objection after evidence review.”]

**Synthesis:** [Why this is the smallest complete scope, how supported
objections were resolved, and why the completion gate passed.]
```

Include every agent used once. Do not include transcripts, tool logs, hashes,
patches, or implementation work.

## Receipt

Return only the runner-provided JSON receipt with `phase: scope`. A successful
phase uses `state: completed` and `result: scoped`. A clarification uses
`state: needs-input` and `result: needs-input`; other failures use
`state: blocked` and `result: blocked`. Include the issue identifier and URL
when known. Set Git and pull-request fields to null.
