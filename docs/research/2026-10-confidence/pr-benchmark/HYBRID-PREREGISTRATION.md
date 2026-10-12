# Mixed-provider peer comparison: separate exploratory preregistration

Design date: 2026-10-12. [hybrid-protocol.json](hybrid-protocol.json) defines a new block before any hybrid solver outcomes. The running 84-trial Opus-only experiment remains frozen and unchanged. Partial infrastructure observations from that experiment motivated this follow-up's stage clocks and backend controls, so this is an exploratory follow-up, not an independently conceived confirmatory test. The registration author ran no solver calls and read no hybrid trial outcomes.

## Four arms and the question

All arms must read the actual supplied `.protocol/SKILL.md` and applicable shipped references. They use the exact current CP0.6 package at `9f3afa68381a510a9d060acb4b8f8bec05888e27`, identical requirements, source, visible checks, scoped-review prompts and fixed stage windows. Only main/peer assignment changes by design; backend-specific tool declarations and Claude-only dollar guards remain disclosed resource asymmetries.

| Arm | Main implementation and repair | Fresh proof-design and adversarial peers |
| --- | --- | --- |
| Astra/Astra baseline | `gpt-6-astra` | `gpt-6-astra` |
| Opus/Opus control | `claude-opus-5-5` | `claude-opus-5-5` |
| Astra/Opus | `gpt-6-astra` | `claude-opus-5-5` |
| Opus/Astra | `claude-opus-5-5` | `gpt-6-astra` |

Both roles are required in every arm: a fresh scoped proof designer before source edits and a fresh adversarial reviewer after implementation. Peers receive requirements, relevant source and raw visible evidence; the main receives their captured reports at the prescribed stages. Reviewers cannot edit production source, read hidden tests/history/gold, recursively delegate or inspect another trial. Missing or truncated review remains a required gap; no model substitution or repeated attempts until a desired verdict appears.

The two primary contrasts change the peer at a fixed main: Astra/Opus versus Astra/Astra, and Opus/Astra versus Opus/Opus. This distinguishes mixed-peer effects from a simple main-model change. The new Opus/Opus arm also controls for this block's timing and adapter design. Comparing a new mixed arm directly with old Opus-only outcomes would confound the model assignment with changed execution conditions.

## Calling Claude through Codex

The efficacy cohort uses an explicit external staged pipeline uniformly in all four arms. The coordinator runs each fresh peer and supplies its report to the main or repair stage. This isolates routing under the declared schedule; it does **not** establish that Codex itself invoked Claude.

To establish the separate delegation capability, a non-task controlled toy must observe an actual Astra/Codex `request_review` call, a bounded Claude adapter invocation, observed Opus peer output returned as a tool result, and subsequent Astra response. Capture model metadata, explicit `medium` effort, tool inventory, output/usage parsing and confinement. A parent launching Claude externally or an offline dummy-auth wire capture is not proof of that callback. Run corresponding actual backend controls before the efficacy cohort. Codex CLI and Claude Code have different built-in tool surfaces; disable those tools or explicitly inventory and mechanically guard equivalent capabilities. Permission prompts alone do not remove a tool. Uncontrolled native shell, patches, apps, plugins, hooks, global skills or hidden-path access invalidate the controlled-envelope claim.

Two exact `gpt-6.1-sol` requests were rejected with HTTP400 on the authorized ChatGPT CLI route. They remain availability failures, not accuracy results. Before freezing this new design, the owner explicitly selected `gpt-6-astra`, whose exact requested route passed an actual availability control. No Sol arm is run or relabeled. Codex's observed CLI stream omits `response.model`, so Astra attribution is **requested_only**: an accepted requested route, not an independently observed response-model identifier. Opus metadata, requested settings and all errors remain separately captured. No authentication change or silent substitution is allowed.

Claude and Codex calls consume independently available provider routes. Offloading can distribute authorized work; it does not increase either provider's account limit or bypass a quota. Actual access, refusal and rate limiting are recorded. Different providers and fresh contexts do not guarantee independent mistakes.

## Stage and resource parity

Every trial shares a 600-second aggregate clock:

| Stage | Maximum seconds |
| --- | --- |
| Fresh proof-design peer | 90 |
| Main implementation, active time | 240 |
| Fresh post-change adversarial peer | 90 |
| Main repair, active time | 120 |
| Startup/terminal persistence reserve | 60 |

Stages are sequential: proof peer, main implementation, adversarial peer, repair, terminal collection. Peer startup/queueing/execution consumes peer and aggregate time outside the main subprocess windows. A review therefore cannot incorrectly consume the main's 240-second timeout. After the adversarial review only the repair window remains. Unused stages do not grant unlimited continuation. The terminal collector persists the scheduled repair-stage main declaration without another model call, task repair or grader hint. If that stage has no valid terminal, final completion stays null. Retain the earlier implementation declaration separately as historical evidence; it cannot certify the repaired tree. Peer completion cannot establish main software completion.

The common mechanically enforced resource control is **wall time**, with the fixed windows above. Current adapters cannot enforce a common rolling token limit or operational-request ceiling before terminal usage arrives. Tokens, cache/reasoning categories and attempted tool requests including refusals are descriptive observed outcomes. Retain raw counters, missing categories and normalization assumptions without double-counting included totals. Do not describe this as equal compute or a token-matched experiment.

Claude additionally receives per-call CLI dollar guards: $0.60 proof peer, $1.75 main, $0.60 adversarial peer and $0.80 repair, totaling $3.75 when all stages use Claude. Mixed arms apply these guards to Claude stages only. Codex exposes no equivalent dollar guard, so this backend-specific asymmetry is a material fairness limitation. A Claude guard can overshoot on an in-flight response. There is no claimed common $4 actual-spending cap, cost parity or subscription billing equivalence.

Missing Codex dollar usage is **null**, never zero. Keep `reported_cost_usd`, post-hoc `rate_estimate_usd` or uncertainty intervals, and actual billing distinct. Directly opened model pages on 2026-10-12 list standard global API references per million tokens: Astra $10 input, $50 output, $1 cache read and $12.50 cache write; Opus $4 input, $20 output, $0.20 cache read, $5 five-minute cache write and $8 one-hour cache write. Astra requests above 272K input have different multipliers. Pin tier/cache/context assumptions when estimating; these references do not establish subscription charges. [Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra), [Opus model](https://platform.claude.com/docs/en/models/opus-5-5/overview).

Both backends use the existing strict terminal JSON: `complete`, `summary` and `remaining`. Role artifacts wrap the actual terminal, natural-language findings, tool/backend receipts and source digests. Do not invent parsed findings arrays or transform a reviewer's completion declaration into independent evidence that software is correct.

The seven operational MCP tools are common, but Codex currently declares three additional MCP resource handlers. Its sole confined `cp_trial` server exposes no resources; that boundary requires explicit controls. Record `strict_seven_tool_parity=false` and the actual declarations rather than claiming an identical seven-tool inventory. Actual unregistered native capabilities or peer source mutation invalidate the controlled-envelope claim.

## Process cleanup boundary

The new process guard owns invocation-local processes launched in a new session. It terminates and kills members of their **original process group**, including surviving group members after the leader exits, and reaps its direct child before capturing final hashes. This is process-group cleanup only: every applicable receipt records `detached_descendants_contained=false`.

A descendant that calls `setsid()` can escape the group and survive cleanup. Existing OS filesystem/network confinement still applies, but lifetime containment is incomplete and writes within its allowed workspace may remain possible. Do not describe process-group test passes as full descendant containment. A captured stream change during cleanup or readonly peer launch/after source drift invalidates the receipt; these guards must be demonstrated before freeze. There is no generic main-source-change-during-cleanup detector or absolute artifact immutability claim. Post-cleanup hashes and independently graded submitted artifacts bound what was actually assessed.

## Tasks, grader controls and freeze

Use all six previously curated tasks—Tweed PR32, PR31, PR40, PR34, PR39 and PR35—with two fresh repeats per arm: **48 new trials**. The separate public [hybrid selection](tasks/hybrid-selection.json) hash is `7033989e8735a734e1d249d7413572c58c2d11ac35a8062ca90edaae681aadb4`; its private manifest hash is `d975e71aaf733d7594c0455f8362cf80a5b5b6c1942797c7448e5df317824472`. PR35 and PR39 are explicitly bounded behavioral slices. Do not select tasks from old or hybrid success, timing, cost or model rankings.

PR32 now uses seven public `run_phase` workflow cases. A retrospective fairness audit after partial old outcomes identified filter-location coupling in the original hidden method-level oracle; the new oracle observes coordinator receipts and process cleanup without requiring one private filter location. Its requirements remain unchanged. PR40 also uses nine public main/resume/storage/native-driver cases after a retrospective audit identified parse-token/private-helper sentinel coupling. The ninth case waits for a real fixture receipt beyond a previously saved deadline and checks no steering, ordinary completion, null persisted budget and process cleanup. Read-only audit found no new disable-sentinel/helper representation requirement. The other four oracles remain unchanged. These are disclosed result-informed, prospective oracle adaptations for the separate exploratory cohort; it does not rewrite or rescore original84 inputs/results. Read-only inspection found no new private method-return or ownership-field requirement in the new seven-case workflow.

All six tasks remain registered. If full-envelope backend or grader controls cannot qualify before execution, hold launch and report the blocker; do not select a favorable subset or substitute tasks. The prospective PR40 nine-case public-CLI audit completed before hybrid outcomes; its new selection hashes above include that correction. Preserve the old primary oracle/cohort and separately frozen eight-case secondary audit unchanged. Backend, resource and exact grader controls still precede launch.

This new block also has an explicit admissibility constraint: preserve configured baseline production files. Edits and allowed ordinary root Python helpers are supported; deleting one of those baseline files is outside the bounded replay projection. Every arm receives the same instruction. An independent PR39 deletion of `bonaparte_linear.py` made actual CLI help fail with `ModuleNotFoundError`, while the sealed oracle restored baseline material and passed. The prospective grader now detects a missing configured file before invoking that oracle and records `unsupported_production_deletion`, `harness_invalid=true` and unknown oracle outcome. The scheduled attempt stays in ITT. No observed oracle failure is fabricated and no sealed oracle or old outcome changes.

This constraint narrows what the experiment can establish: it cannot certify legitimate deletion/refactor alternatives outside this replay envelope or whole-application preservation. Reviewers explicitly receive role-only terminal semantics: `complete` means their review assignment is finished, findings and proposed checks belong in `summary`, and `remaining` contains unfinished required review work. Peer completion never means the software task is correct, and peers cannot implement it.

The new exact grading adapter must pass every selected base-fail/head-pass and visible-baseline-pass control, plus relevant equivalent-implementation and path/isolation checks. When adapter/source projection changes, old control receipts are insufficient. In particular, a partition or import mechanism must not produce an apparent software failure by hiding legitimate modules or forcing accepted helper names. All oracle/head/history material remains outside solver configuration, environment and child-process access. Fresh workspaces, main/peer contexts and evidence prevent cross-trial state reuse.

Freeze the new protocol, runner/adapters, grader, parsers, schemas, role prompts, package/task snapshots, resource-monitoring rule and complete 48-tuple queue after these controls and before hybrid outcomes. The scheduling algorithm is fixed in the JSON. Record concurrent old-cohort activity and provider queue/rate-limit effects; do not alter the old scheduler to favor hybrid arms. Any later correction creates a dated separate experiment, retaining original attempts.

## Outcomes and analysis

Primary correctness is observed held-out acceptance/preservation success on the submitted production tree with source/test-integrity rules. Neither CP validation nor model agreement establishes that outcome. False completion requires a valid `complete=true` and an observed oracle failure; unknown completion or unavailable grading remains unknown. Truthful success additionally requires empty remaining work and both required peer stages completed with no required review gaps. A captured peer terminal with `complete=false` is an incomplete review, not a passed stage.

Keep all scheduled tuples in assigned intention-to-treat denominators, including incomplete, rate-limited and harness-invalid attempts. Only an observed valid pass contributes to verified-success numerator; do not invent a failed oracle when grading never ran. Preserve raw outcomes, invalidity reasons and model-conforming/known-graded sensitivity analyses with their denominators. One linked identical-config infrastructure retry is allowed only for a proven pre-solver setup failure or transport failure before any assistant response. Solver failure, missing peers, denied operations and exhausted budgets are not retry-until-success events.

Autonomy metrics include guard denials, requested reviews, missing peer stages, rate limiting, time exhaustion and observed token usage and external task-specific human help. Automated reviews and mechanical policy enforcement are not human intervention. Report stage/token/time breakdowns and cost observability separately; do not compare a known Claude value to a fabricated Codex zero.

Average the two repeats in each task-arm cell, then compare paired task means for each fixed-main peer contrast. Publish every cell, task difference, wins/losses/ties and denominator. Use descriptive exact whole-task bootstrap enumeration with both repeats kept together: 6^6 = 46,656 resamples, and inverse-empirical-CDF percentile ranks. No significance-based winner or precise population effect follows from six purposive tasks.

This compares model-plus-provider-harness routing under common wall windows and controlled operational capabilities. Vendor system prompts, tokenization, caches, runtimes, resource-handler declarations and Claude-only dollar guards still differ; the study cannot isolate model architecture. It cannot prove general accuracy, independence, production persistence or increased account quotas. Its separate preregistration protects the old cohort from result-driven changes while making any hybrid accuracy and delegation claims inspectable.
