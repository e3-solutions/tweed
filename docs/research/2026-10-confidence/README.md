# Confidence Protocol: current models, harnesses, and autonomous proof

Research date: 2026-10-12. This dossier accompanies the 0.6.0 proposal. It separates
documented capabilities, inspected implementation, actual executed probes, design
inference, and work not completed. The result improves evidence gates and recovery;
it does not establish a general increase in model accuracy on complex tasks.

## Read the findings

- [Models and Claude Code](models-and-claude.md): GPT-6.1 Sol, GPT-6 Astra,
  Opus 5.5, prompting, effort, context, permissions, hooks, delegation and evaluation.
- [Harnesses and other projects](harnesses-and-projects.md): pinned Codex, T3 Code,
  OpenHands, Aider, LangGraph, Inspect AI and SWE-bench source, licenses and limits.
- [Protocol analysis and independent proof design](protocol-analysis.md): traced
  existing behavior, counterexample matrix, design dissent and independently
  reproduced failures.
- [Agent audit](agent-audit.json): actual parent receipts, hashes, session references,
  model usage, spawn/completion counters and blocked/partial execution qualifications.
- [Targeted mutation results](mutation-results.json) and
  [reproducible mutation runner](evaluate_mutations.py): four passing controls and
  four guard-removal mutants rejected by actual regression-test assertions.
- [Smaller models in normal use](cheap-depth/README.md): shipped routing policy,
  actual Luna/Terra support work, Haiku5.5 triage qualification, and cost-observability
  limits. This addition is outside the historical studies' frozen package.

Repository-only research and tests are excluded from the plugin release. The
installed skill loads a short core and routes complex tasks/harness questions into
conditional references instead of importing this whole dossier into every task.

## What changed in the models and harnesses

GPT-6.1 Sol is the documented lower-cost choice near Astra capability; Astra targets
the most demanding tasks. Both support substantial reasoning effort and tool use
through Responses, with product-specific differences in available settings. Opus
5.5 uses always-on adaptive thinking and is positioned for long-running agentic
coding. These are vendor contracts, not access to internal training, weights or
hidden reasoning. Choose model/effort through representative task evaluation rather
than a fixed ranking. [Sol model](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[GPT-6 guide](https://developers.openai.com/api/docs/guides/latest-model),
[Claude models](https://platform.claude.com/docs/en/models/overview).

Modern harnesses increasingly own durable sessions, context compaction, programmatic
tool execution, delegation, permission enforcement and recovery. The implementation
boundary matters: Codex desktop, CLI, Responses and managed Agents API are different
surfaces; Claude hooks have event-specific enforcement; T3 Code adapts provider
capabilities rather than making every provider equivalent. Runtime acceptance,
actual execution, durable side effects and product correctness remain separate
judgments. [Codex platform](https://developers.openai.com/blog/codex-as-a-platform),
[Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview),
[Claude hooks](https://code.claude.com/docs/en/hooks),
[pinned T3 adapter](https://github.com/pingdotgg/t3code/blob/48595c787cf5ffe3fcc089ce36754d7c601e4007/packages/provider-core/src/server/ProviderAdapter.ts).

We borrowed patterns, not upstream implementation code: durable proof state from
checkpointed graphs, scoped delegation from agent SDKs, routed context from
repository maps, and refusal oracles from evaluation harnesses. We rejected a new
orchestration runtime, blanket hook enforcement, universal maximum effort, fixed
agent quotas for ordinary work, and reviewer agreement as a confidence score.
All eight project snapshots and their licenses are recorded in the detailed report.

## Concrete improvements

| Problem | Resulting behavior | Rejection proof |
| --- | --- | --- |
| A flat report cannot express prerequisite proof. | Optional `depends_on` DAG, validated ancestor closure and deterministic next work. | Unknown edges, cycles, deep chains, early pass, stale/tampered ancestors. |
| Replacing upstream support leaves downstream pass labels. | Atomic transitive demotion to partial, retaining old evidence. | Chain/diamond, changed status/run IDs, unchanged repeat and details-only control. |
| Role names alone lack attributable review. | Contract opt-in, pinned required roles, scoped records, artifact/contract hashes and captured review runs. | Missing records/roles, same identity, incomplete scopes, drift and unresolved findings. |
| A fresh review from repository B can cover proof from A. | Software review roots must match every scoped supporting root. | Before-fix public CLI acceptance; rejection afterward, same-root and split-root controls. |
| A planned read-only command writes shared telemetry or invokes Git fsmonitor. | Explicit telemetry bypass and fsmonitor disabled in fingerprint reads. | File snapshots, live HTTP observer, executable fsmonitor sentinel. |
| Copied evidence changes the fingerprint exclusion anchor. | New captures retain their original evidence location. | Public CLI copy/handoff pass; original source changes still reject. |
| Record-only metadata edits can hide newly added source or change exit status. | Additional `capture_sha256` binds known execution/source/exclusion fields and log digest; impossible stopping statuses reject. | Metadata-only edits rejected without log changes; recomputed impossible-status control. |
| Deep JSON and legacy start metadata escape as tracebacks. | Safe reader refusal and historical v1 research interpretation. | Independently reproduced failures; public CLI regressions. |
| Support bundles discard current capture version/kind. | Preserve safe v2/content provenance without paths, argv or work output. | Actual capture plus strict redaction assertions. |

Required missing proof stays partial. A ready frontier never runs free-text
verification instructions. Empty readiness is distinct from completed evidence.
Current software reviews require source binding; proof design may reference
historical source but remains bound to current intent and an intact captured artifact.

## Research and testing audit

Forty native research agents were spawned: three initial eight-agent panels plus
two replacement eight-agent panels. All reported completion. Initial model/project
panels contained denied web calls; their unsupported vendor recollections were not
promoted. Source-grounded replacement panels and independent pinned-source inspection
support the vendor/project facts. The protocol panel read the actual local code.

Twenty-six native testing agents were spawned: three eight-agent panels and two
replacement testers for blocked/help-only assignments. Native counters report
twenty-five completions. One parent returned `completed` with seven of eight workers
complete; resumption recovered partial mutation results, while its background
repository-suite job was killed. We do not convert that narrative into an eighth
verified completion. Replacement testers executed the missing artifact and malicious
verification cases. The requested broad testing work occurred; individual denied
or incomplete attempts are still visible rather than counted as successful proof.

Substantive workers were configured for `claude-opus-5-5`; observed model metadata
and, where inspected, child transcripts support that attribution. Haiku helper
requests used for web processing are disclosed. This is local harness evidence, not
provider-authenticated identity or statistically independent reviewer sampling.
The list-price usage estimates are not a claim about subscription charges.

Tool availability did not imply permission. Empty parent denial arrays did not imply
successful child source retrieval. Parent prose also miscounted executed test calls.
We reconciled owned child results and retained both failed and repaired receipts.
The final acceptance proof comes from current local regression captures and CI,
not from subagent counts, anecdotes or unchecked parent summaries.

## Evaluation scope and real PR experiments

The core began with 179 passing regressions. New tests exercise the actual CLI,
real Git source, captures, artifact hashes, source relocation and HTTP telemetry.
The mutation experiment passes each control before disabling one guard; every
selected mutant must fail by assertion, not syntax/import/runner failure. It tests
four targeted guard removals, not mutation coverage of every branch. The separate
project panel rejected eight meaningful mutations and identified one equivalent
mutation; its attempt to run the repository suite against all mutants was killed,
so that coverage remains unverified.

To establish behavioral efficacy, freeze a task set and independent acceptance
oracles, then compare baseline and new protocol with the same model, effort,
harness, budgets and dependencies. Include ordinary bug fixes, multi-component
features, trust/persistence boundaries, restart/compaction, denied tooling, stale
proof, contradictory sources and attempted false completion. Rotate repeated trials
across Sol, Astra and Opus and vary one factor at a time. Keep held-out failures out
of worker prompts. Grade the final user-visible state as well as the transcript.

Report escaped defects, false completion, unresolved required proof, user
interventions, recovery correctness, task completion, time, tokens and cost, with
denominators, variation and invalid/denied runs visible. A cheaper route only wins
if consequential correctness is preserved. Cross-model review is a testable
hypothesis, not an automatic proof multiplier.

The [real PR replay report](pr-benchmark/README.md) now records six proposed
approaches against CP0.5 on six historical public PR tasks, with two repeats:
84 assignments, 82 independently graded receipts and two interrupted outcomes
retained as unknown. CP0.6's nominal4/12 versus3/12 acceptance difference comes
entirely from an interrupted baseline pair; its11 complete-pair task difference
is zero. Separate public-behavior audits exposed representation coupling in two
old acceptance oracles. The original scores, code and registration remain intact;
posthoc audit results are reported separately. This does not establish improved
model task accuracy.

Actual Codex-to-Claude callback controls also passed, with runtime-observed Opus5.5,
executed peer checks, a denied peer source write and a returned receipt subsequently
used by Codex. The first mixed-provider block had invalid workspace-tool transport
and cannot rank accuracy. The separately sealed V2 block qualifies full staged
execution, actual baseline commands, timeouts, source/lifecycle metadata and an
independent grader before historical-task dispatch. Its fixed-main peer-provider
contrasts remain exploratory, with unknown Codex dollar cost and model attribution
limits. [Bridge proof](pr-benchmark/BRIDGE-PROOF.json),
[V2 registration](pr-benchmark/HYBRID-V2-REGISTRATION.json).

## Limits and rollback

Legacy contract v1/report v3 and historical captures stay readable. Older CLI
versions ignore the new graph/policy extensions and cannot enforce them. Opted-in
contracts without pinned roles retain report-declared roles; explicit pinned roles
prevent removing a required role only from the report. A writer can still change
the accepted contract or recompute hashes to forge provenance. Hashes do not
authenticate reviewers, prove substantive review, or prevent collusion.

Git inventory excludes ignored/external inputs and cannot detect a transient change
and restore. Source roots are filesystem/content observations, not authenticated
repository identity. Arbitrary review artifacts can be source inputs unless finalized
before capture or intentionally ignored. Copied reports inspect their recorded roots
and never certify the caller's checkout. Windows, production task accuracy and
real external persistence remain outside this deterministic acceptance scope.

Rollback is a Git revert of this PR. Remove optional dependency/policy fields only
when deliberately returning to legacy semantics; do not edit historical run files.
No global plugin installation, user settings, external hook or production service
is changed by this proposal.

## Collective work used

The following Forum posts informed explicit choices. Explained feedback receipts
were saved for all five posts fully read; the unrelated archive-retention post
received abstain. These sources teach internal methods, not current vendor facts.

- **Enforce side-effect isolation mechanically in agent-documentation experiments**:
  restricted research inventories and bounded evaluation envelopes.
- **Keep terminal result capture outside an agent's operational tool budget. In bounded coding…**:
  actual receipts, source-bound review and truthful partial terminal outcomes.
- **Evaluate tool-only collection nodes as proposal, guard, and side-effect contracts**:
  proposal/acceptance/persistence separation and refusal tests.
- **Compact routed repository guidance preserved correctness while reducing coding-agent tokens**:
  keep the invariant skill core compact and route conditional detail; preserve the
  post's bounded single-repository/model applicability limits.

One prior-session search was opened with its exact returned source handle before
implementation. Its passages supported scoped proof/partial-result discipline;
they did not establish current vendor/model behavior. Current facts were checked
against official documents and pinned upstream source separately.
