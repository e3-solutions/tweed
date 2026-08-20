# Bonaparte research and design rationale

Last verified: 2026-08-19

This document records the research, public documentation, and open-source workflow patterns used
to design the instruction-only Bonaparte skill in [`skills/bonaparte/SKILL.md`](../skills/bonaparte/SKILL.md).
It is a design ledger, not a claim that Bonaparte's exact role counts or phase topology have been
scientifically proven. Many multi-agent studies use logic, mathematics, or code-generation
benchmarks rather than full repository delivery. Bonaparte therefore treats empirical results as
directional evidence and exact agent counts as a conservative operational policy that can be routed
by risk and uncertainty. Deterministic repository checks are authoritative only for the obligations
they actually encode and exercise; non-author review must also examine whether those checks are an
adequate oracle.

## Contents

- [Executive synthesis](#executive-synthesis)
- [How research maps to Bonaparte](#how-research-maps-to-bonaparte)
- [Multi-agent debate, diversity, and conformity](#multi-agent-debate-diversity-and-conformity)
- [Software engineering agents and repository planning](#software-engineering-agents-and-repository-planning)
- [Review and verification research](#review-and-verification-research)
- [Skills and public orchestration patterns](#skills-and-public-orchestration-patterns)
- [Ideas deliberately not adopted](#ideas-deliberately-not-adopted)
- [Validation evidence](#validation-evidence)
- [Limitations and update policy](#limitations-and-update-policy)

## Executive synthesis

The research did not support a simple rule such as “more agents are safer.” The strongest combined
conclusion was narrower:

1. Multiple agents can surface errors or evidence that one reasoning path misses, but debate is
   sensitive to protocol, task, model strength, and tuning. It does not reliably beat simpler
   ensembles or deterministic checking.
2. Same-model agents can exhibit correlated errors in studied homogeneous configurations. A fresh
   thread excludes known conversational anchors but does not create statistical independence or by
   itself prove a causal reduction in anchoring. Distinct evidence sources, falsifiable objectives,
   tools, or models are more valuable than duplicate seats.
3. Majority pressure can suppress a correct minority. Bonaparte therefore uses blind first passes
   and explicit preservation of dissent as a policy intended to limit exposed anchors, not as a
   scientifically established guarantee against conformity.
4. Agent topology should respond to uncertainty and risk. Local changes with decisive executable
   proof can use fewer reviewers; ambiguous causal, cross-boundary, or high-risk work should add a
   genuinely distinct evidence channel.
5. Software delivery benefits from specialization—investigation, proof design, writing, and
   non-author review—but specialization is useful only when responsibilities and stop conditions are
   explicit.
6. Repository work requires dependency and change-impact planning, not merely file-level patching.
7. LLM reviewers are fallible and biased. Their role is to generate falsifiable findings and inspect
   proof coverage; executable tests, traces, manifests, and version-control identity are authoritative
   only for the obligations they encode and exercise.
8. Review must bind to an exact candidate. Any content or proof change invalidates stale review and
   requires review of the new fingerprint.

These conclusions produced Bonaparte's decision frontier, blind first passes, adaptive councils,
proof-before-writer gate, task/ambient manifests, evidence-based disagreement protocol, bounded
correction loop, and exact-candidate non-author review.

## How research maps to Bonaparte

| Bonaparte mechanism | Evidence or precedent | Design interpretation |
|---|---|---|
| Decision frontier before each phase | Adaptive debate and topology studies; Agentless | Spend agent calls only on questions that can change the outcome. |
| Blind, context-isolated first passes | LLM conformity studies; controlled debate study; subagent documentation | Exclude already-known conversational anchors before agents establish evidence; causal reduction of anchoring in repository work remains unverified. |
| Distinct causal tracer and falsifier | Debate research; OpenAI debate framing; Bonaparte policy | Make disagreement purposeful and falsifiable rather than conversational role-play. |
| No claim of statistical independence | Knight–Leveson; diversity/scaling studies | Fresh context is an isolation property, not a probability guarantee. |
| Adaptive role counts | G-Designer; DOWN; communication-pruning work; Agentless | Use conservative defaults, with explicit evidence-based up- and down-routing. |
| Central reconciliation plus executable discriminator | Debate limitations; LLM-judge bias; SWE-bench | Votes prioritize diagnostics; tests, traces, and contracts close software proof obligations. |
| Dependency/change-impact graph | CodePlan | Plan affected consumers and re-plan after interface-affecting changes. |
| Proof artifact before writer | AgentCoder; CodeT; test-driven public workflows | Define the oracle before implementation can overfit the visible patch. |
| Writer/non-author separation | AgentCoder; modern code-review studies; public review skills | Do not let patch authors approve their own interpretation of correctness. |
| Frozen task and ambient manifests | OpenAI implementation-final-review skill; repository review practice | Review the exact task-owned candidate while preserving unrelated user changes. |
| Review invalidation after correction | OpenAI final-review skill; Superpowers review loops | A clean verdict applies only to the fingerprint inspected. |
| Shared-worktree serialization | Parallel-agent guidance and worktree documentation | Avoid review races and overlapping writers in one mutable filesystem. |
| Bounded non-convergence | Public review-loop skills; agent failure taxonomy | Stop oscillation instead of manufacturing consensus or silently widening scope. |
| Incident causality separated from static susceptibility | Bonaparte policy | Do not claim that a plausible code smell caused an observed incident without trigger, mechanism, boundary, and evidence against alternatives. |
| Lifetime and boundary-invariant tests | Software testing principle; Bonaparte policy | Exercise when an invariant must hold and across which caller/provider boundary, not merely whether a value exists. |
| Coordinator-only external mutations | Bonaparte safety policy | Keep issue, Git, remote, and delivery identity changes serialized under one accountable owner. |
| Duplicate-safe resume and delivery identity | Bonaparte delivery policy | Reconcile existing branches, commits, and pull requests before creating new external state. |
| Preserve ambient user work | Bonaparte workspace-safety policy | Separate task-owned content from pre-existing or unrelated workspace state and never absorb it silently. |

## Multi-agent debate, diversity, and conformity

### Foundational and positive evidence

- [AI safety via debate](https://openai.com/index/debate/) (OpenAI, 2018) frames adversarial
  argument as a way for one agent to expose flaws in another agent's proposal and reduce a complex
  dispute to a claim a judge can directly evaluate. It also explicitly notes that debate offers no
  correctness guarantee and may be computationally expensive. Bonaparte adopted the “surface the
  decisive dispute” idea, but replaces a persuasion-oriented judge with repository evidence whenever
  possible.

- [Improving Factuality and Reasoning in Language Models through Multiagent Debate](https://proceedings.mlr.press/v235/du24e.html)
  (Du et al., ICML 2024 archival paper) reports improved reasoning and factuality when multiple model instances propose
  and debate answers over several rounds. This supported adversarial critique as a useful test-time
  mechanism, but not a universal software-delivery topology.

- [Can LLM Agents Really Debate? A Controlled Study of Multi-Agent Debate in Logical Reasoning](https://arxiv.org/abs/2511.07784)
  (Wu et al., 2025 preprint) finds that intrinsic reasoning strength and group diversity dominate
  structural parameters, while majority pressure can suppress independent correction. This directly
  motivated blind collection, preservation of minority findings, and diverse evidence lenses.

- [Demystifying Multi-Agent Debate: The Role of Confidence and Diversity](https://aclanthology.org/2026.findings-acl.1694/)
  (Findings of ACL 2026 archival paper) studies why vanilla debate can underperform simpler voting and emphasizes confidence
  and diversity. Bonaparte uses confidence only to route follow-up diagnostics; it never treats
  confidence totals as proof.

- [Hear Both Sides: Efficient Multi-Agent Debate via Diversity-Aware Message Retention](https://arxiv.org/abs/2603.20640)
  (2026 preprint) focuses on retaining diverse information rather than every message. This reinforced
  central reconciliation of claims and evidence instead of broadcasting full transcripts.

### Negative and limiting evidence

- [Should we be going MAD? A Look at Multi-Agent Debate Strategies for LLMs](https://proceedings.mlr.press/v235/smit24a.html)
  (Smit et al., ICML 2024 archival paper) finds that tested debate systems do not reliably outperform
  self-consistency or multiple reasoning paths without careful tuning. Bonaparte therefore does not
  use debate as its correctness oracle and avoids open-ended rounds.

- [Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models?](https://proceedings.neurips.cc/paper_files/paper/2025/hash/934252acd87f254d5d4672fbde283bd2-Abstract-Conference.html)
  (Choi et al., NeurIPS 2025 archival paper) reports that majority voting explains much of the gain commonly
  attributed to debate and that debate alone does not improve expected correctness in its model.
  Bonaparte consequently requires targeted falsification and correction-oriented evidence, not debate
  for its own sake.

- [On scalable oversight with weak LLMs judging strong LLMs](https://proceedings.neurips.cc/paper_files/paper/2024/hash/899511e37a8e01e1bd6f6f1d377cc250-Abstract-Conference.html)
  (Kenton et al., NeurIPS 2024 archival paper) presents task-dependent, mixed evidence for debate-style scalable oversight.
  This cautioned against claiming that an LLM review council can guarantee correctness.

- [Conformity in Large Language Models](https://aclanthology.org/2025.acl-long.195/)
  (Zhu et al., ACL 2025 archival paper) finds conformity toward majority responses, including incorrect ones, and
  studies devil's-advocate mitigation. Bonaparte withholds earlier conclusions during first passes and
  gives falsifiers an explicit counterexample-seeking role.

- [An Empirical Study of Group Conformity in Multi-Agent Systems](https://aclanthology.org/2025.findings-acl.265/)
  (Choi et al., Findings of ACL 2025 archival paper) reports alignment with numerically dominant groups and stronger
  agents in simulated debates. This reinforced the decision not to resolve software disagreements by
  majority or perceived agent authority.

- [Conformity, Confabulation, and Impersonation: Persona Inconstancy in Multi-Agent LLM Collaboration](https://aclanthology.org/2024.c3nlp-1.2/)
  (Baltaji et al., C3NLP 2024 workshop paper) finds that multi-agent discussion can expose diverse perspectives but
  also produces conformity and unstable opinions; instructions to defend an opinion can worsen that
  instability. Bonaparte therefore assigns falsifiable questions and evidence rather than persistent
  personas or debate-for-debate's-sake.

- [Judgment under Uncertainty: Heuristics and Biases](https://pubmed.ncbi.nlm.nih.gov/17835457/)
  (Tversky and Kahneman, Science 1974 archival journal paper) is the classic human evidence for anchoring and related
  heuristics. It was used as conceptual background—not direct LLM evidence—for withholding the
  coordinator's hypothesis from blind first passes.

- [Humans or LLMs as the Judge? A Study on Judgement Bias](https://aclanthology.org/2024.emnlp-main.474/)
  (Chen et al., EMNLP 2024 archival paper) documents biases and adversarial vulnerability in both human and LLM
  judges. Bonaparte requires reproducible evidence for findings and treats deterministic checks as
  authoritative over reviewer verdicts.

### Adaptive topology and diversity

- [Debate Only When Necessary: Adaptive Multiagent Collaboration for Efficient LLM Reasoning](https://arxiv.org/abs/2504.05047)
  (2025 preprint, DOWN) supports selectively invoking debate rather than paying its cost for every
  input. Bonaparte's decision frontier and deterministic down-routing apply this principle to software
  phases.

- [G-Designer: Architecting Multi-agent Communication Topologies via Graph Neural Networks](https://proceedings.mlr.press/v267/zhang25cu.html)
  (Zhang et al., ICML 2025 archival paper) learns task-adaptive communication graphs and reports large reductions in
  communication cost on its benchmarks. Bonaparte does not adopt its learned graph, but does adopt
  the more general idea that topology should vary with task difficulty and risk.

- [Cut the Crap: An Economical Communication Pipeline for LLM-based Multi-Agent Systems](https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html)
  (ICLR 2025 archival paper) targets redundant multi-agent communication. It supported removing duplicate roles,
  restricting cross-agent messages to disputed claims, and declining seats that add no new question
  or evidence channel.

- [Understanding Agent Scaling in LLM-Based Multi-Agent Systems via Diversity](https://openreview.net/forum?id=9BN2W5BCfE)
  (ICLR 2026 AIMS workshop paper) reports diminishing returns for homogeneous agents and stronger gains from different
  models, prompts, or tools in its studied configurations. Together with older multiversion evidence,
  this supports the narrower policy that same-model fresh threads are context-isolated but must not be
  assumed statistically independent; it does not establish universal correlation.

- [An Experimental Evaluation of the Assumption of Independence in Multiversion Programming](https://doi.org/10.1109/TSE.1986.6312924)
  (Knight and Leveson, IEEE TSE 1986 archival journal paper) found correlated failures across independently developed program
  versions beyond what an independence assumption predicted. It is not an LLM study, but it provides
  a durable warning against treating separately produced solutions as independent samples merely
  because their production processes were separated.

- [Why Do Multi-Agent LLM Systems Fail?](https://proceedings.neurips.cc/paper_files/paper/2025/hash/b1041e52d3be19f0a9bc491657488e4a-Abstract-Datasets_and_Benchmarks_Track.html)
  (Cemri et al., NeurIPS 2025 archival datasets-and-benchmarks paper) introduces a failure taxonomy covering specification, coordination,
  and verification problems. Bonaparte responds with explicit phase contracts, bounded ownership,
  manifest identity, and stop conditions rather than assuming orchestration itself creates safety.

## Software engineering agents and repository planning

- [AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation](https://arxiv.org/abs/2312.13010)
  (2023 preprint) separates programmer, test designer, and test executor roles and reports gains on bounded
  code-generation benchmarks. Bonaparte adopted proof/writer separation, but made a fresh test
  designer conditional because the paper does not establish that every repository edit needs a
  separate designer.

- [CodeT: Code Generation with Generated Tests](https://openreview.net/forum?id=ktrw68Cmu9c)
  (ICLR 2023 archival paper) shows the value of generated tests and execution for selecting code without requiring a distinct
  agent identity for every test artifact. This supported making the proof artifact mandatory while
  allowing existing tests or deterministic analysis when the oracle is already unambiguous.

- [CodePlan: Repository-level Coding using LLMs and Planning](https://www.microsoft.com/en-us/research/publication/codeplan-repository-level-coding-using-llms-and-planning-2/)
  (FSE 2024 archival paper) models repository work as incremental planning with dependency analysis, change-may-impact
  analysis, adaptive replanning, and correctness oracles. Bonaparte directly adopted an explicit
  dependency/change-impact graph, affected-consumer tracing, packet ordering, and replanning after
  interface changes.

- [ChatDev: Communicative Agents for Software Development](https://aclanthology.org/2024.acl-long.810/)
  (ACL 2024 archival paper) organizes specialized agents across design, coding, and testing phases. It informed phase and role
  separation, while Bonaparte adds blind first passes, exact candidate manifests, and evidence-based
  disagreement to reduce conversational convergence.

- [MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework](https://proceedings.iclr.cc/paper_files/paper/2024/hash/6507b115562bb0a305f1958ccc87355a-Abstract-Conference.html)
  (ICLR 2024 archival paper) uses standardized operating procedures and role-specific intermediate artifacts. Bonaparte adopted
  explicit return schemas, phase contracts, and bounded role responsibilities rather than free-form
  agent discussion.

- [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering](https://proceedings.nips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html)
  (NeurIPS 2024 archival paper) demonstrates that the interface between an agent and repository tools materially affects software
  performance. This reinforced precise tool boundaries, repository inspection, and focused diagnostic
  commands instead of treating orchestration prompts as sufficient.

- [Agentless: Demystifying LLM-based Software Engineering Agents](https://conf.researchr.org/details/fse-2025/fse-2025-research-papers/85/Demystifying-LLM-based-Software-Engineering-Agents)
  (FSE 2025 archival paper) shows that a comparatively simple localization–repair–validation pipeline can be competitive on
  SWE-bench. It was important negative evidence against role inflation. Bonaparte preserves a reduced
  path for local, low-risk work with decisive executable proof.

- [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://openreview.net/forum?id=VTF8yNQM66)
  (ICLR 2024 archival paper) evaluates issue resolution in real repositories through execution-based tests and cross-file
  changes. It supported Bonaparte's requirement that every acceptance criterion have direct evidence
  at the exact final candidate rather than relying on plausible prose or a reviewer vote.

## Review and verification research

- [Modern Code Review: A Case Study at Google](https://research.google/pubs/modern-code-review-a-case-study-at-google/)
  (Sadowski et al., ICSE SEIP 2018 archival paper) studies motivations, practice, and challenges across millions of
  reviewed changes. Bonaparte adopts lightweight, change-focused review and does not treat review as
  a replacement for automated checks.

- [Expectations, Outcomes, and Challenges of Modern Code Review](https://www.microsoft.com/en-us/research/publication/expectations-outcomes-and-challenges-of-modern-code-review/)
  (Bacchelli and Bird, ICSE 2013 archival paper) reports defect discovery, code understanding, knowledge transfer,
  and alternative solutions as review outcomes. This supported non-author review with separate
  contract/simplicity and correctness/integration lenses.

- [Convergent Contemporary Software Peer Review Practices](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/rigby2013convergent.pdf)
  (Rigby and Bird, ESEC/FSE 2013 archival paper) observes convergent review practices across projects while also
  showing that reviewer counts vary with change complexity. It supports review as a distinct gate but
  not a universal LLM reviewer count.

- [Do Code Review Measures Explain the Incidence of Post-Release Defects?](https://doi.org/10.1007/s10664-020-09837-4)
  (Krutauz et al., Empirical Software Engineering 2020 archival journal paper) finds that relationships between review measures and defects are
  not stable enough to treat review process metrics as a correctness guarantee. This reinforced
  Bonaparte's reliance on direct proof rather than reviewer quantity or activity.

- Human code-review observations were used only as analogy, not as proof that two same-model LLM
  reviewers are optimal. Bonaparte's two-reviewer default is explicitly an assurance policy; the
  second reviewer is conditional for low-risk, directly provable local changes.

## Skills and public orchestration patterns

These are operational precedents, not controlled scientific evidence.

### Skill format and concision

- [Agent Skills specification](https://agentskills.io/specification) defines the `SKILL.md` package,
  metadata, optional resources, progressive disclosure, and recommended size limits. It supports
  Bonaparte's pure-skill implementation and the decision to keep this research ledger outside the
  runtime skill folder.

- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills) and the
  [OpenAI skills catalog](https://github.com/openai/skills) informed trigger-focused frontmatter,
  imperative instructions, context-conscious length, validation, and forward-testing on realistic
  tasks.

- [OpenAI's practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)
  emphasizes starting with simpler arrangements and adding multi-agent complexity when it improves
  outcomes. Bonaparte applies that principle through adaptive routing rather than a fixed maximal
  council.

### Fresh review and exact fingerprints

- [OpenAI Agents JS implementation-final-review skill](https://github.com/openai/openai-agents-js/blob/main/.agents/skills/implementation-final-review/SKILL.md)
  uses fresh-context reviewers, risk-tiered reviewer specialties with fixed two-reviewer multiplicity,
  a frozen fingerprint, complete-diff review, content-change invalidation, bounded correction rounds,
  and final deterministic repository checks.
  These are direct operational precedents for Bonaparte's task manifest and review loop.

- The same pattern is also visible in the
  [OpenAI Agents Python implementation-final-review skill](https://github.com/openai/openai-agents-python/blob/main/.agents/skills/implementation-final-review/SKILL.md),
  providing a second maintained example of separating implementation from final review and binding
  conclusions to exact content.

### Subagent-driven development patterns

- [Superpowers: subagent-driven development](https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md)
  uses fresh implementers, specification review, quality review, correction loops, and broad final
  review. Bonaparte adopted fresh writer/reviewer separation, but made packet review conditional to
  avoid unnecessary layers for one-packet changes.

- [Superpowers: dispatching parallel agents](https://github.com/obra/superpowers/blob/main/skills/dispatching-parallel-agents/SKILL.md)
  recommends one agent per independent domain and warns against parallelizing related work. This
  informed shared-worktree serialization and isolated-worktree requirements for parallel writers.

- [Superpowers: writing plans](https://github.com/obra/superpowers/blob/main/skills/writing-plans/SKILL.md)
  informed the definition of an implementation packet as the smallest independently testable vertical
  result worth a separate gate.

- [Superpowers: requesting code review](https://github.com/obra/superpowers/blob/main/skills/requesting-code-review/SKILL.md)
  provides a concrete handoff pattern for requirement, base, candidate, and review findings. This
  influenced Bonaparte's compact report schemas and exact-candidate briefs.

### Context isolation and team routing

- [Claude Code subagents documentation](https://code.claude.com/docs/en/sub-agents) describes fresh
  context windows, focused prompts, tool restrictions, and the trade-off between subagents and a main
  context. It reinforced sanitized self-contained briefs and the rule that unavailable context
  isolation blocks a blind gate.

- [Claude Code agent teams documentation](https://code.claude.com/docs/en/agent-teams) recommends
  teams for research, review, competing debugging hypotheses, and separable cross-layer work while
  warning about coordination cost and same-file conflicts. Bonaparte uses those positive cases but
  centralizes reconciliation and avoids teammate socialization before blind reports are collected.

## Ideas deliberately not adopted

The source review rejected or narrowed several tempting designs:

- **No universal “more agents is better” rule.** Homogeneous agents can show correlated errors and
  diminishing returns in studied configurations; debate gains are inconsistent, and coordination has
  real cost.
- **No claim that fresh threads are statistically independent.** Bonaparte uses the term
  “context-isolated” and seeks diverse evidence channels.
- **No open-ended round-table debate.** It risks conformity, context pollution, and expensive
  non-convergence. Bonaparte uses blind first passes, one evidence-focused rebuttal, and a direct
  discriminator.
- **No majority vote as software proof.** Votes and confidence may select the next diagnostic; they
  cannot replace a reproducible test, trace, contract, or manifest comparison.
- **No fixed eight-seat minimum.** Exact counts are policy defaults, not empirical optima. Local work
  can down-route when a decisive check resolves the sole uncertainty.
- **No mandatory proof-designer agent for every packet.** The proof artifact is mandatory; a fresh
  designer is triggered only when the oracle is ambiguous, novel, or high risk.
- **No author self-approval.** A writer's tests and explanation are evidence inputs, not final review.
- **No parallel writers in one shared worktree.** Separate file ownership is insufficient when
  review fingerprints and shared commands can still race.
- **No clean-review credit after content changes.** Corrections create a new candidate and invalidate
  routed verdicts.
- **No claim that static or protocol tests establish empirical multi-agent effectiveness.** They
  validate the written state machine; realistic forward tests probe runtime behavior.

## Validation evidence

Research shaped the protocol. Two checks are reproducible against the current uncommitted candidate:

- `python3 /Users/aryagm/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/bonaparte`
  reports `Skill is valid!`.
- `python3 -m unittest -v tests.test_bonaparte_skill_v0` passes 17 protocol scenarios covering phase
  admission, maximum live children, proof-before-writer ordering, review-only immutability,
  task/ambient manifest separation, correction invalidation, and post-commit equivalence.

The files exercised by those commands had these SHA-256 identities when the checks were run on
2026-08-19:

```text
214941a7f2122accdf62caea50ae4c8ddb57f571c46e885c2820fde2c260cc5b  skills/bonaparte/SKILL.md
1b8421cda2031ea84719c141f40ce433c6c0df17a5a1fb4945e847eb639322f1  skills/bonaparte/agents/openai.yaml
938c8bee82649507392ffb1f1810a7b404be7c612bf87443280d600bae6aa846  tests/test_bonaparte_skill_v0.py
```

The remaining items are historical development reports from the session that produced this v0. No
durable transcript or commit-bound artifact accompanies them, so they should be treated as unverified
reports rather than independently reproducible evidence:

- The complete repository suite passed 207 tests after the final compression.
- A context-free forward test used the skill on a deliberately misleading payment retry bug. Blind
  investigators established the idempotency-key lifetime failure; the scope challenger rejected a
  superficial “header exists” test; the proof designer required a commit-aware oracle. Two fresh
  whole-diff reviewers then found two additional flaws after initial green tests: mutable header reuse
  across the gateway boundary and a vacuous identity assertion caused by copied snapshots. Each
  correction invalidated review, restarted both reviewers on a new manifest, and ended with both
  reviewers passing the exact final candidate.
- A failure-path test confirmed that unavailable subagents stop the workflow instead of silently
  falling back to coordinator-only judgment.

If accurate, these reports show that the instructions activated the intended workflow in
representative cases. They do not prove general correctness, are not a research result, and do not
measure Bonaparte against every alternative topology.

## Limitations and update policy

- Research entries are labeled as archival papers, workshop papers, or preprints. Remaining preprints
  should be revisited when archival versions or replications appear.
- Reasoning benchmarks and bounded code-generation benchmarks do not directly establish optimal
  behavior for long-running repository delivery.
- Human code-review studies provide useful process analogies but do not validate same-model LLM
  reviewer counts.
- Public skills and vendor documentation demonstrate workable implementation patterns, not causal
  evidence that those patterns improve every task.
- Bonaparte's exact thresholds—two default reviewers, three concurrent children, one rebuttal, and
  three finding-bearing rounds—are disclosed operational limits chosen for safety, cost, and
  non-convergence control. They are not research-derived constants.

When updating Bonaparte, add a source here only if it materially affected a design decision. Record
contradictory evidence and scope limitations alongside positive findings. Prefer primary papers,
official documentation, and maintained source repositories over summaries. Re-run protocol tests and
a context-free forward test after any change to role routing, blindness, manifests, or review gates.
