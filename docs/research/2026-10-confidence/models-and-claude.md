# Models and Claude Code: Confidence Protocol research

Research date: 2026-10-12. This report separates **verified documentation**, **locally observed harness behavior**, **design inference**, and **unresolved empirical questions**. Published model capability is not proof that a particular account, harness, or integration supports it. No model's confidence statement establishes software correctness.

## Current model contracts

| Model | Verified API contract | Consequence for Confidence Protocol |
| --- | --- | --- |
| GPT-6.1 Sol (`gpt-6.1-sol`) | 1,050,000 context; 128,000 output; low/medium/high/xhigh/max effort, medium default; none/minimal unsupported. Tool calling uses Responses; Chat Completions lacks tool calling. Standard input/output $2/$10 per million tokens. | Route routine complex work here as an initial hypothesis; escalate only after measuring unresolved obligations. Validate API fields separately from the app's visible effort options. |
| GPT-6 Astra (`gpt-6-astra`) | 1,050,000 context; 128,000 output; low/medium/high/xhigh/max effort. Standard input/output $10/$50 per million tokens. | A stronger model can be useful for difficult proof design, but its higher nominal price does not establish better defect detection per dollar. |
| Claude Opus 5.5 (`claude-opus-5-5`) | Released September 22, 2026; 1M context; 128K output; adaptive thinking always on; medium default effort. Standard input/output $4/$20 per million tokens. | Preserve the exact ID in delegation receipts. Calibrate effort per task. A resumable session and its output artifacts matter more than a narrative claim that Opus was used. |

Sources opened during research: [Sol model](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra), [Opus 5.5 overview](https://platform.claude.com/docs/en/models/opus-5-5/overview). Pricing is API pricing, not an assertion about subscription billing or marginal cost for this run. The exact harness may expose different supported settings; do not mechanically translate an app effort value into an API request.

### Reasoning, evidence, and response compatibility

**Verified:** Opus 5.5 rejects disabled thinking, explicit thinking-token budgets, and forced `tool_choice` modes. The output cap includes thinking and answer tokens. Thinking blocks must be preserved unmodified when continuing tool loops. It is unsafe to assume that the first content block contains the answer. Some between-tool progress messages now arrive in thinking blocks and can be empty under the default display. [Opus 5.5 changes](https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5), [migration guide](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide).

**Inference:** CP should request concise explanations, counterexamples, decisions, and observable evidence. It should not require reproduction of private internal reasoning as a proof artifact. Absence of visible thinking or progress text is neither inactivity nor task failure. Parse content by type, honor terminal stop reasons, and record truncation/refusal separately from successful completion. No integration gain is claimed until its parser and continuation path are exercised against actual returned events.

**Verified:** Effort labels are not calibrated identically across model generations. Anthropic recommends explicit effort sweeps; xhigh/max can increase thinking substantially. [Opus 5.5 prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5). **Inference:** Begin research and routine review at the documented default, then raise effort when measured counterexample discovery or task completion improves. Treat a whole-run budget as a separate control from a per-response token cap.

## Prompt changes with practical significance

**Verified:** OpenAI recommends removing duplicate instructions, unnecessary examples, and irrelevant tools one group at a time, rerunning representative evaluations after each change. Its reported internal gains are workload-dependent, not guaranteed CP improvements. The same guide recommends explicit delegation scope and acknowledges excessive testing on small tasks. [GPT-6 guide](https://developers.openai.com/api/docs/guides/latest-model).

**Verified:** Astra may interpret restrictive boundaries literally and stop work that the user intended to continue. OpenAI suggests narrow, explicit authorization for safe local workflows and selecting documentation based on the task. [Rethinking skills and prompts for Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra).

**Inference:** Preserve CP's compact invariant core: define disprovable obligations; bind evidence to actual source; distinguish structural validation from product truth; retain required missing proof as partial. Put task-specific procedures in optional references. Avoid a compulsory full repository tour, a fixed agent quota, repeated passing tests, or universal high effort. These can consume the budget needed to examine difficult boundaries.

A proposed autonomy instruction should be concrete: continue authorized discovery, implementation, disposable local tests, failure repair, and draft-PR preparation; stop only when the next action actually requires additional authority or missing information. Record that boundary so a resumed worker does not invent a broader grant. Scope is a product requirement, not a friction-removal target.

## Claude Code harness mechanisms and limits

### Context and compaction

**Verified:** Claude Code clears old tool output and summarizes as context fills; detailed earlier instructions can disappear. Persistent instructions and focused compaction guidance help. Skills load their full content on demand. Fresh subagents isolate their input context; forked agents inherit the conversation. [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works).

**Inference:** A compact summary is a navigation aid, not authoritative proof or a new permission grant. Persist the accepted objective, requirement/obligation IDs, authorization boundary, source fingerprint, evidence paths, unresolved findings, active processes, and next eligible action outside conversation history. After compaction or resume, reload this small packet, inspect current source, and reuse only evidence whose source and environment still match.

### Subagents and review independence

**Verified:** Native subagents have separate contexts, prompts, tool access, permissions, and transcripts. Custom agents can set full model IDs. Forking copies the existing conversation and removes ordinary input isolation. Transcripts survive parent compaction and can be resumed within the session, subject to retention. Worktree isolation is a distinct option. [Claude Code subagents](https://code.claude.com/docs/en/sub-agents).

**Inference:** Isolation is useful, but neither a fresh context nor a different model guarantees statistical independence. A reviewer fed the implementer's conclusion and only selected logs can inherit the same blind spot. Capture reviewer origin, exact question, source/evidence inspected, findings, and unresolved issues. Separate proof design from implementation and review the actual resulting change afterward. Dispatch workers by disjoint responsibility and reconcile changes before collecting release proof.

An eight-person panel is useful here because the user requested broad research. It should not become the default for typo fixes or ordinary bugs. The quantity of agents is an execution fact; diverse counterexamples and binding proof are the quality signal.

### Permissions and hooks

**Verified:** `dontAsk` denies calls that would need a prompt; it does not grant all tools displayed in the tool list. Auto mode uses an action classifier. Allow rules and deny rules remain relevant. [Claude Code permissions](https://code.claude.com/docs/en/permissions).

**Verified:** Hook outcome depends on both event and returned data. Exit 1 usually does not enforce a policy; exit 2 blocks some events, while `PostToolUse` occurs after the action and cannot prevent it. New failure-blocking configuration has event-specific limitations. [Hooks reference](https://code.claude.com/docs/en/hooks).

**Inference:** CP's portable command should decide readiness through an explicit exit status that an adapter intentionally maps into that harness's event contract. Do not assert enforcement merely because a hook file exists. Test missing script, invalid JSON, nonzero exit, timeout, and stale source through the actual event path. Stop hooks should not spin forever trying to repair a forbidden action or silently turn partial evidence into complete. Report capability denial and continue other authorized work.

### Checkpoints and cancellation

**Verified:** Claude's file checkpoints persist across resume, but edits made through shell commands or external processes are not captured; remote side effects are outside their rollback scope. [Checkpointing](https://code.claude.com/docs/en/checkpointing).

**Inference:** Use git/source fingerprints and explicit artifact receipts to reason about shell-generated edits. A cancelled foreground tool can leave child processes or external operations alive. A harness tool result, process exit, and side-effect reconciliation are distinct observations. Interrupted checks stay partial until process outcome, relevant files, and any consequential external state have been reconciled. Rollback guidance must describe the actual boundary being reversed.

### Durable autonomous work

**Verified, historical context:** Anthropic's 2025 long-running harness experiment used initialization, explicit feature state, incremental work, progress files, and end-to-end checks to address incomplete handoffs and premature completion. It explicitly left multi-agent superiority unresolved and focused on web apps. [Long-running harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents).

**Inference:** Reuse the durable obligation-state pattern, not a rule that every project needs hundreds of features or an initialization script. Add reviewability to each checkpoint: what changed, which obligations now have current evidence, which remain unresolved, and which action comes next. Run a minimal actual behavior check before resuming a complex task if the workspace may have changed; do not indiscriminately rerun the entire suite.

## Recommended CP adaptations and falsification tests

These are implementation proposals derived from the verified contracts above. They are not vendor promises.

| Priority | Adaptation | What can disprove its adequacy |
| --- | --- | --- |
| P0 | Durable accepted objective and obligation graph, with dependency-aware next actions | Resume after compaction, interrupt, or source drift; any dropped obligation, incorrect dependency readiness, or widened authority is failure. |
| P0 | Freshness-checked resume packet containing source and evidence references | Change source or environment between checkpoint and resume; old passing evidence must not authorize completion. |
| P0 | Explicit reviewer receipt and unresolved-finding gate | Forge reviewer role labels, omit origin/reference, reuse review for a previous source state, or leave a blocker; readiness must fail. |
| P0 | Harness/model capability recording with truthful denied/partial states | Request an unsupported model/effort/tool; a narrative answer or successful process exit must not be mistaken for the requested execution. |
| P1 | Optional harness adapters for event-specific hook semantics | Missing executable, timeout, malformed output, denied tool, and cancelled process must yield visible gaps without enforcement claims. |
| P1 | Model-routing experiments on frozen tasks and independent expected outcomes | A cheaper path that saves tokens but misses a consequential boundary cannot be promoted on aggregate success alone. |
| P1 | Context-pressure checkpoints and focused readback | Deliberately omit a requirement from the conversation summary; persisted obligations must restore it and keep the outcome partial. |
| P2 | Explainable budget and stall handling | Repeated no-progress attempts must stop with an unresolved obligation and reason; budget exhaustion cannot produce a completed report. |

### Evaluation design

**Verified:** Official evaluation guidance distinguishes the agent's transcript from the resulting environment state, recommends repeated trials, and combines deterministic, model, and human graders according to the task. Model judges need calibration rather than blind acceptance. [Anthropic agent evaluation](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), [OpenAI evaluation practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices). **Historical caution:** Anthropic documented benchmark contamination in nine of 1,266 BrowseComp problems under a multi-agent evaluation. This is evidence that evaluation isolation matters, not a measured failure rate for these new models or for CP. [Evaluation awareness study](https://www.anthropic.com/engineering/eval-awareness-browsecomp).

Hold task requirements and acceptance checks constant while changing one of prompt shape, model, effort, or routing. Include ordinary fixes, dependency-heavy refactors, external-contract changes, interruption/resume, unavailable tooling, stale evidence, contradictory research, and adversarial completion attempts. Evaluate successful user-observable outcome, escaped defects, false completion, unnecessary permission stops, recovery correctness, wall time, token use, and cost.

Record exact model and harness versions and actual usage; a requested model name does not establish actual attribution. Compare repeated trials on the same task set because model outputs vary. Keep held-out tasks and defect expectations separate from worker prompts. Report denominators and failures, not only the best run. A promising route must maintain or improve evidence sufficiency and consequential-defect detection; lower cost alone cannot justify a weaker proof gate.

Cross-model review is an experiment worth testing. It is not an automatic proof multiplier. Prefer diverse roles and independently chosen counterexamples over agreement counts. A unanimous panel can still be wrong, while a single concrete reproduction can refute it.

## Rejected defaults and tradeoffs

| Rejected default | Why | Retained useful part |
| --- | --- | --- |
| Every task gets max effort and many subagents | No established universal gain; latency and context overhead can reduce actual boundary testing. | Escalate effort and delegation where representative trials show benefit. |
| A longer protocol is a safer protocol | Redundant restrictions can suppress initiative or crowd out relevant facts. | Keep a small invariant core and load consequential details when required. |
| Hooks are a portable correctness gate | Events have different semantics; failure can be non-blocking. | Explicit adapters plus event-path verification. |
| Compaction or checkpoints prove resumability | Summaries can lose rules; shell and remote effects are not generally reversible. | Durable state plus current source/process/side-effect reconciliation. |
| Different model equals independent proof | Shared input and biased evidence selection can correlate failure. | Separate design/review roles, origin records, raw evidence, and counterexample prompts. |

## Research execution evidence

The requested research panel uses one Claude Code parent and eight explicitly named native Agent researchers on `claude-opus-5-5`, with read-only tools and no CLI fallback. The launch and final JSON output are stored locally under `.confidence/research/models-*`. Two runs were retained:

| Run | Session ID | Native agents | Source access | Model observation |
| --- | --- | --- | --- | --- |
| Initial | `02cfd6c2-0e33-42fd-9e65-7d8bfbbc8961` | 8 spawned, 8 completed, one per configured topic | 12 actual nested permission denials; Sol/Astra retrieved no primary sources, so those reports remain unsupported for vendor facts. | Every child transcript's assistant message model is `claude-opus-5-5`. |
| Grounded | `c9a05ecd-0aeb-4051-aa4f-6f4e1bb36088` | 8 spawned, 8 completed, one per configured topic | 126 successful WebFetch/WebSearch results across all eight; zero nested permission denials. Explicit authorization of the six read-only research tools retained `dontAsk` for other actions. | Every child transcript's assistant message model is `claude-opus-5-5`. |

The source-grounded panel covers all eight topics and is the research panel counted toward the requested broad investigation. Initial blocked findings are retained as diagnostic history. The grounded receipt reports an approximately $7.72 list-price usage estimate, including Haiku requests used by the harness for web processing; subscription billing was not established. Thus the eight researchers and parent were observed using Opus, while every internal request was not exclusively Opus.

The parent JSON reported `permission_denials: []` even in the initial run. Inspecting only that aggregate would have missed child tool denials. Inspection used the exact owned session's transcripts and checked actual tool-result denial messages; searching for the word “denied” alone also matches documentation describing permissions and falsely inflates counts. `.confidence/research/models-grounded-transcript-receipt.json` records child IDs, model observations, successful web-result references, and transcript hashes. These are local, version-specific observations, not authenticated attestations by the model provider. WebFetch summaries can truncate or distort a long page, so the coordinator's independently opened documents support the report's verified facts.

The coordinator independently opened the linked primary documents. Subagent summaries inform design proposals; they do not replace primary-source checking or executed proof of CP behavior. This research does not claim a comparative model-performance improvement. That requires the controlled evaluation above.

One panel finding was rejected after checking the source: the evaluation researcher claimed that the prompt-ablation citation above belonged only to a GPT-5.6 guidance page. The directly opened GPT-6 guide explicitly contains the incremental-removal and repeated-evaluation guidance in its “Favor leaner prompts” section. This concrete disagreement illustrates why an adversarial review finding must be investigated, not automatically adopted. A reviewer count, distinct prompt, or source URL can coexist with an incorrect conclusion.

The locally installed CLI reports `2.1.285 (Claude Code)`. Online documentation includes version-gated behavior, sometimes newer than that installation. The research invocation uses flags present in local `claude --help`; features described only by later documentation need a separate capability probe before adoption. Do not infer that a current documentation page describes every older installed binary.

## Executed testing and resulting corrections

The separate testing panel used eight native Opus agents with narrow schema, policy, coverage, identity, artifact, contract, source-freshness, and migration assignments. Session `a06785c4-43af-4741-bd21-f1e9f38d34fd` reports eight spawned/completed, one per configured role. All eight child transcripts observed `claude-opus-5-5`. A scoped `Bash(python3 *)` allow rule permitted the local Python test commands, while 26 actual nested command denials were retained. Seven testers executed checks; the artifact tester attempted forbidden `git`/`shasum` prerequisites and did not reach the required Python tests. It was not counted as an executed tester.

A replacement native artifact tester, session `16adec67-ef9d-4a7f-b3de-aef13ff2a175`, executed three exact permitted Python commands, without broadening access. Its child transcript observes Opus 5.5, no nested denials, and `OK` outputs for 3, 1, and 2 test invocations. These are six invocations across five distinct artifact/path cases. The parent narrative miscounted these totals; the raw tool results establish the counts. Thus this lane produced eight testers with meaningful executed checks, plus one original blocked artifact assignment retained as diagnostic history. No unsupported novel counterexample was counted as executed proof.

The original provenance module's 25 public-CLI tests passed. The contract tester also executed 14 novel cases. Some other novel scripts were denied because their command strings did not fit the narrow allow rule; read-only findings from those testers remain proposals until independently reproduced. Local usage estimates were approximately $4.59 for the eight-agent testing panel and $0.20 for artifact replacement. `.confidence/research/models-testing-transcript-receipt.json` and `models-artifact-repair-transcript-receipt.json` retain executed command results separately from denials.

### Reproduced defect and regression proof

**Observed before the correction:** a real disposable git fixture recorded behavior proof for obligation P1 in repository A. A critic run captured in unrelated, unchanged repository B was attached to P1. Public `validate --require-complete` returned exit 0 and displayed both source roots. Freshness alone proved that B had not changed; it did not prove that B was the source under review. The result, source hash, control result, and command output were retained in `.confidence/research/models-reconcile-probes.json`.

**Correction and observed proof:** software review records now have to match the source root of each supporting run for their scoped obligations. A regression test rejects the unrelated-repository case. Another accepts different working directories within the same repository, and a two-repository task accepts separate review records scoped to P1 and P2 respectively. A record for one root cannot claim an obligation supported by additional unreviewed source. Historical proof design retains its documented freshness exception; source association remains distinct from review identity or truth.

**Contract-role correction:** required role labels were initially stored only in the report, so a report edit could remove an integration-review requirement. The optional `review_policy.required_roles` now pins a nonempty unique list of known roles in the accepted contract. Completion combines pinned roles with report-declared roles. Tests reject malformed pinned lists and prove that dropping the report label/record cannot drop the contract requirement. Existing opted-in contracts without the new list retain compatibility.

After these corrections, the expanded provenance module ran 29 tests together successfully; two additional focused tests then verified multi-repository scoped review and rejection of unreviewed supporting source. The repository owner performs the final full-suite capture after all source writes. These checks demonstrate the validator boundaries exercised; they do not measure improved arbitrary-task model performance.

### Limits preserved after adversarial review

The executed contract probes also showed that a writer controlling the report can recompute its contract digest to associate old output with new intent, and that removing both the opt-in policy and records restores the legacy path. Local hashes detect accidental drift relative to retained metadata, not forgery or an externally immutable contract. These are trusted-writer and compatibility boundaries, and the report must disclose them.

A regular file with a matching hash does not establish substantive review content. A captured command can succeed while its nested agent was denied; the output must be inspected. A declared model or reviewer identity is not authenticated. Unicode look-alike identity strings were proposed as a further ambiguity, but the narrow counterexample command did not execute and the advertised comparison remains trimming/case folding. Deep JSON and type-coercion findings outside the changed review boundary likewise remain separately scoped proposals. The patch's completeness gate is a consistency/evidence gate, and its valid completion report is not proof that every substantive software claim is true.
