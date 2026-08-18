# Bonaparte Solution Scope

Turn the supplied Linear request into the smallest implementation-ready solution
scope. For a bug, start from its established RCA. For a feature, start from the
requested outcome and verified repository behavior. The runner supplies only
the selected intake, latest RCA, or latest existing scope needed for this phase.
Keep repository work read-only. Use Linear only to publish and verify the final
scope comment; keep every other external-system interaction read-only.

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

- Use the supplied issue kind. A bug requires an established
  `## Bonaparte · Root Cause Analysis` handoff. A feature receives its intake and
  must not invent or require an RCA. A missing kind returns `needs-input`; a bug
  without an established RCA returns `blocked`.
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

## Scoping workflow

1. Record the exact request, constraints, acceptance clues, and supplied
   evidence. For a bug, record the established causal chain and responsible
   boundary. For a feature, characterize current behavior and the requested
   outcome without assuming an implementation. Record the repository path, Git
   `HEAD`, and relevant clean/dirty worktree state. If repository evidence
   materially contradicts the handoff, return `blocked` with the smallest
   re-investigation needed.
2. Scan the coverage map for material gaps in outcome, interfaces and consumers,
   failure behavior, data and compatibility, operations, and proof. Prioritize by
   impact times uncertainty. Investigate facts; ask only when a user-owned choice
   can change the solution contract.
3. Use zero to three read-only agents total for the phase, including any reviewer
   or specialist, and only for distinct frontier assignments. The coordinator may
   combine applicable axes for a narrow change:
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
4. Require each child to return at most 350 words: recommendation, source
   locations, rejected excess, material risks, confidence, and missing
   information. Keep conclusions blind when that reduces anchoring.
5. Synthesize the smallest complete candidate. Every proposed change must map
   to the bug's RCA mechanism, the feature's requested outcome, or an observable
   acceptance criterion.
6. Give every acceptance criterion one smallest decisive proof and owner:
   - **Simple local logic:** a coordinator-owned deterministic check may suffice.
   - **External/native protocol:** verify the installed primary contract and
     captured or live behavior.
   - **Process lifecycle:** inject exit, error, or interruption and prove cleanup.
   - **Persistence/concurrency:** prove interruption, retry, and competing access.
   - **Producer-consumer boundary:** run an end-to-end consumer canary.
   Changed non-local boundaries require fresh read-only verification in both
   implementation and review. Combine compatible obligations under one verifier;
   do not verify boundaries the change does not touch.
7. Express the candidate as the smallest complete vertical slices that preserve a
   runnable, verifiable state. Put a risky contract or test seam early when that
   reduces uncertainty; do not create horizontal layer tickets with no observable
   outcome.
8. If the request cannot fit one coherent implementation packet, propose ordered
   valuable packets and ask which comes first. Do not publish an omnibus scope.
9. Apply adversarial checks directly, delegating within the zero-to-three total to
   one fresh reviewer only for a named objection or unresolved decision. Require
   only material objections and the minimum correction.
10. Add one specialist within that same total only when a named unresolved risk
   cannot be decided from repository evidence or the coordinator's current
   analysis. Do not add an agent or round without a specific unresolved question.
11. Reconcile supported objections. Re-read cited evidence and confirm `HEAD`
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
- implementation slices are ordered, locally executable, and independently
  verifiable; and
- no material evidence-backed objection remains unresolved.

If one user decision can close the gap, return `needs-input` and explain its
consequence in `summary`. Otherwise return `blocked` with the smallest missing
investigation; never invent architecture.

## Linear comment

Handle an existing scope by schema state:

- Current (`**Status:** Scoped`): validate it against the completion gate and
  return it without another comment only when it passes.
- Immediately preceding schema (`### Proof obligations` and `### Debate map`, but
  no current status): carry its contract forward, revalidate material repository
  facts, and rewrite it in the current schema without redesigning it.
- Incomplete, stale, or older: return `blocked` with the missing contract fact or
  investigation.

For a new or upgraded scope, publish one terminal `scoped` comment.

After writing, re-read the comment and return `completed` only if it matches
this schema and contains the evidence required by the completion gate.

```markdown
## Bonaparte · Solution Scope

**Status:** Scoped

### Handoff basis
- RCA basis: [causal chain and responsible boundary, or “Not applicable — feature”]
- Constraints carried forward: [material issue/RCA constraints]
- Reuse: [verified built-in, project utility, or installed library; custom gap if any]

### Handoff basis
- Request outcome: [exact issue outcome this scope delivers]
- RCA link (bug): [established causal chain and responsible boundary, or “Not applicable — feature”]
- Constraints carried forward: [material issue/RCA constraints]

### Outcome
[Smallest complete outcome and how it resolves the bug or delivers the feature.]

### Change surface
| File or boundary | Current evidence | Exact responsibility | Interface/caller effect |
|---|---|---|---|
| [`path` or boundary] | [`file:line` or result] | [bounded change] | [effect or None] |

### Implementation slices
1. **[Step]**
   - Target: [component/path]
   - Depends on: [step or “None”]
   - Change: [bounded responsibility]
   - Verify: [proving check]

### Acceptance and proof
| Observable criterion | Boundary | Smallest decisive check | Owner |
|---|---|---|---|
| [trigger → outcome] | [boundary type] | [direct check] | [coordinator/verifier] |

### Guardrails
- Non-goals: [excluded work and why]
- Risks/safeguards: [evidence-backed risk → proportional safeguard and proving check]
- Decision basis: [chosen direction and evidence; strongest rejected alternative]
- Assumptions/open decisions: None
- Broader validation: [justified repository-supported checks, or “None.”]
- Post-merge: [external rollout/live validation, or “None.”]

### Repository state
- Repository: [absolute path]
- HEAD: [commit]
- Worktree: [clean or relevant dirty state]
```

Publish the durable contract, not the scoping process. Do not include agent
identities, transcripts, tool logs, unrelated hash data, patches, or
implementation work.

## Receipt

Return only the runner-provided JSON receipt with `phase: scope`. A successful
phase uses `state: completed` and `result: scoped`. A clarification uses
`state: needs-input` and `result: needs-input`; other failures use
`state: blocked` and `result: blocked`. Include the issue identifier and URL
when known. Set Git and pull-request fields to null.
