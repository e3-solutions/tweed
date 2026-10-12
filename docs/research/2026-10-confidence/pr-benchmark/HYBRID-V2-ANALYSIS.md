# Closed V2 mixed-provider analysis — 12 October 2026

The two registered fixed-main comparisons showed opposite observed acceptance differences in this exploratory replay. With Astra main, Opus peers accepted 2/12 submissions against 5/12 with Astra peers. With Opus main, Astra peers accepted 8/12 against 5/12 with Opus peers. These are two separately registered, same-main comparisons on six selected historical PR tasks. They do not establish a general benefit from mixing providers, a vendor ranking, or an improvement caused by Confidence Protocol itself. The descriptive task-bootstrap intervals for both acceptance differences include zero. [Preregistration](HYBRID-V2-PREREGISTRATION.md), [sealed protocol](hybrid-v2-protocol.json), [exact analysis](HYBRID-V2-ANALYSIS.json).

All **48 assignments** produced raw receipts and independently bound grades: 12 per arm, two repeats for each of six task clusters. No assignment is missing, harness-invalid or unknown in its final oracle outcome. The [public projection](results/hybrid-v2/results.json) includes all 48 assignments; its [artifact inventory](results/hybrid-v2/artifact-hashes.json) binds every raw receipt, grade and submitted production patch. A closed receipt means the attempt was preserved and graded; it does not mean the model completed every required stage or passed the task.

| Main provider / peer provider | Assigned | Accepted submissions | Strict completion success | Both required peers closed | Repair terminal unknown | False completion / observed declaring-complete denominator |
|---|---:|---:|---:|---:|---:|---:|
| Astra / Astra | 12 | 5 | 3 | 8 | 6 | 0/3 |
| Opus / Opus | 12 | 5 | 0 | 5 | 0 | 1/2 |
| Astra / Opus | 12 | 2 | 1 | 3 | 2 | 0/1 |
| Opus / Astra | 12 | 8 | 1 | 8 | 3 | 0/3 |

An accepted submission passed the sealed acceptance oracle on an eligible final production tree. Strict completion success additionally requires a valid repair-stage `complete=true`, no remaining required work, and both required scoped peers completed with no unfinished review work. Peer completion refers to finishing the assigned proof-design or adversarial-review role; agreement and a terminal declaration do not prove its reasoning correct. A false completion requires an eligible repair-stage `complete=true` and an observed oracle failure. Its table denominator includes only eligible declaring-complete runs with known oracle outcomes, not all 12 assignments; an unknown terminal is not a truthful partial report or an observed false completion. Proof-packet quality and semantic correctness beyond the executed acceptance oracle remain **unassessed**, even for strict completion successes.

The primary contrasts retain the same main provider and change only the scheduled peer-provider assignment within this V2 workflow. Both use **12 paired trial cells and six whole-task clusters**. Each task's two repeats are averaged before computing the paired task difference. Exact empirical whole-task resampling enumerates **6⁶ = 46,656** ordered resamples. The displayed 95% descriptive intervals use inverse empirical-CDF percentile ranks; they describe this small purposive task set and are not precise population-effect, significance or generalization claims. The two repeats do not increase the number of independent task clusters.

| Registered contrast, intervention minus same-main control | Acceptance difference | Exact descriptive 95% task-bootstrap interval | Task wins / losses / ties | Strict completion difference | Strict descriptive interval |
|---|---:|---:|---:|---:|---:|
| Astra main: Opus peers minus Astra peers | −25 percentage points | [−58⅓, 0] percentage points | 0 / 2 / 4 | −16⅔ percentage points | [−33⅓, 0] percentage points |
| Opus main: Astra peers minus Opus peers | +25 percentage points | [0, +58⅓] percentage points | 2 / 0 / 4 | +8⅓ percentage points | [0, +25] percentage points |

The exact acceptance task differences are shown below. Negative values mean fewer accepted submissions for the intervention within that task's two repeats; these rows are not six additional comparisons selected after observing the result.

| Task cluster | Astra main: Opus peers minus Astra peers | Opus main: Astra peers minus Opus peers |
|---|---:|---:|
| Tweed PR31 | 0 | 0 |
| Tweed PR32 | −1 | +1 |
| Tweed PR34 | 0 | 0 |
| Tweed PR35 | 0 | +½ |
| Tweed PR39 | 0 | 0 |
| Tweed PR40 | −½ | 0 |

Because all final acceptance outcomes are known and eligible, the valid complete-case acceptance sensitivity has the same 12 pairs, six clusters and point differences as the primary acceptance analysis. Logical verified-acceptance bounds collapse to the observed values in this cohort. The analyzer still keeps separate rules for unknown future inputs: known ineligible assignments contribute fixed zero to verified acceptance without inventing an oracle failure; eligible null acceptance and missing receipts with unknown validity can remain logically unresolved. Terminal-known paired false-completion event-indicator comparisons have different observable pair counts: six pairs/four clusters at Astra main and nine pairs/six clusters at Opus main. These pairs can include complete=false terminals; they are distinct from the arm rates conditioned on declaring complete above. Their reduced denominators are disclosed in the exact JSON and should not be interpreted as equal-sized truthfulness experiments.

Dollar observation is incomplete and this study did not match tokens or dollars. Whole-arm reported totals are **unknown for every arm**. Codex stages omit dollar cost; the Astra/Astra arithmetic known subtotal of zero represents no observed dollar-bearing stage costs, not a free run. Opus/Opus has 11 known complete trial totals and one partial-cost trial, so even that arm's total is unknown. Known values are harness-reported estimates, not observed bills or subscription charges.

| Main / peers | Complete trial dollar totals known | Sum of those known complete totals | Known stage subtotal, including partial trials | Whole-arm dollar total |
|---|---:|---:|---:|---:|
| Astra / Astra | 0/12 | Unknown | No observed dollar-bearing stages | Unknown |
| Opus / Opus | 11/12 | $22.0564532 | $23.9795716 | Unknown |
| Astra / Opus | 0/12 | Unknown | $12.1311962 | Unknown |
| Opus / Astra | 0/12 | Unknown | $14.4522768 | Unknown |

There are zero complete dollar-observed pairs for either primary contrast. Wall duration is observable, but not a substitute for cost or successful completion: mean paired task duration differences were −118.823 seconds with Astra main/Opus peers and +96.585 seconds with Opus main/Astra peers. These reflect whole staged attempts, including short or incomplete stages. They are descriptive provider-harness observations, not evidence of improved compute efficiency. Provider system prompts, tokenization, caching, runtime and Claude-only dollar guards differ. Concurrent coordinator Opus calls, a Haiku pilot, reviews and other work also created **uncontrolled provider load** during this replay; that background load was not randomized or matched.

The measured package is the exact CP0.6 archive at revision `9f3afa68381a510a9d060acb4b8f8bec05888e27`, with common role instructions, task material, corrected public oracles and fixed 90/240/90/120-second stages within a 600-second aggregate envelope. Later shipped small-model routing, intent-flow guidance and subsequent review-driven changes were not in this archive and are **not evaluated by these 48 assignments**. V2 is a prospectively sealed follow-up informed by earlier infrastructure observations, not an independently conceived confirmatory experiment. The original 84-assignment comparison and invalid first 48-assignment mixed-provider block remain separate and are not pooled here. PR35 and PR39 are bounded slices; results do not establish whole-application preservation or success on arbitrary complex tasks.

This cohort uses explicit external stages with fresh scoped peers. Actual Codex-to-Claude native callback capability was demonstrated separately in [bridge proof](BRIDGE-PROOF.json). That capability proof is distinct from an accuracy effect of the staged experiment. Astra's accepted requested route remains **requested-only attribution**: the response model identity and live wire tool inventory are unobserved, so these data do not authenticate actual returned Astra weights. The Claude stages recorded Opus runtime metadata; a requested effort setting does not expose hidden reasoning. Different model families do not by themselves establish independent errors.

Both final observer roles passed their complete 48-assignment checks with no recorded violations, no hosted inference or oracle calls of their own, and no solver feedback. The metadata observer bound the sealed registration, governing inputs, raw receipts, grades and exact normalized rows. The distinct stream observer checked actual reported stream metadata and durable solver-material hashes. Closed analysis required their role-specific source/sidecar bindings, distinct audit bytes, complete identities, preserved material, current captured stream hashes, and the [sealed closure](results/hybrid-v2/closure.json). It separately rechecked **96 hash-bound oracle stdout/stderr files**, with no unbound-present or absent-unrecorded oracle outputs. These are declared provenance and consistency checks; they do not authenticate an auditor's authorship, prove independent reasoning, or establish uninterrupted absolute immutability. Both observers began after trial launch; their preserved records do not establish uninterrupted prelaunch observation or exclude transient changes before their coverage. Original-process-group cleanup does not contain descendants that detach into a new session.

The public receipt projection and 48 byte-preserved patches support inspection of the submitted changes. Raw model transcripts, private logs and personal paths are not published. Input hashes bind the private audit/material originals used at closure; a hash alone does not reproduce withheld evidence. The complete source-binding and definition inventory is in [the exact analysis JSON](HYBRID-V2-ANALYSIS.json), produced by [the closed-study analyzer](analyze_hybrid_v2.py).

| Evidence identity | SHA256 |
|---|---|
| Public prospective registration | `db078f1bf1219be7316f2579d39e02b150134a505b8dc7d2e3871f1231d5abbc` |
| Sealed protocol | `fb1d855a539eaff82a39e1b87fca23a4bc6931ae2690c7258a857563b4746423` |
| Frozen 48-assignment schedule | `e9f386420185a5f17f69fb2a80752c71b74dd8f67dd61787fd968cfe5e6eeb66` |
| Original normalized analysis input | `5ceb5d5b9a887703e52d0c44a4d3881797a24032faab5457af3515ebf4476809` |
| Private closed-study manifest, referenced by public closure | `f497b95101602f96318775caf5ac87034dd9d43ee926db2c17083ee8c397865d` |
| Metadata observer final audit | `4e5464ee09a0b93c834eb7c81c0bfd21e98d942a4be9dcfa7d26270a816b3558` |
| Stream observer final audit | `c99d17f434055f00d2a8f852b843f17ef22a077032cb4965440ef1693218d04c` |
| Metadata observer source | `770cacd19829db54de35a5e4d0f4a3d5a1eb92cf8a867bb46d6f539d15e71ec9` |
| Stream observer source | `ef4b4cb1de2b74e4010479f220d96d933ae64ed2fa65985a0f793a0c0565cb8e` |
| Durable stream/material seals | `250323f6c332596aeb14a00de56164d00d887db8a30698067e4a27aebda1d149` |
| Public result projection | `9afe8e0af565b192e369dbfb1272a1a0ed3760e15d046cb48d8e650ff31e50b9` |
| Public closure projection | `2f06112335b4fe87482143ff25345e7da3f6bd02660f2689962f8de82d264d93` |
| Public artifact hash inventory | `2f55b0b5ba8f0df6d806c180e9350cb03a0c1eab97b2e14eff8d8b26dc170696` |
| Published exact analysis JSON bytes | `54b923831ff2e64853d88b944f95d1cda2b7583b17a2116497e3d31f557ee59a` |
| Canonical analysis payload, excluding its digest/scope fields | `b111b361a1c87c4fd8ea78743d39fc6a4d60188cd6c6a71c53367d487fd67c95` |

The analyzer's initial independent review found and reproduced three defects: ineligible rows expanding verified-success bounds, unchecked post-audit oracle logs, and duplicate audit schemas being accepted as two observers. Corrections preserved those reproductions and were checked with **48 synthetic tests plus 16 fresh independent correction controls** before closed-study use. Those controls qualify the analysis boundary and do not add model-trial successes or enlarge the six-task efficacy sample.
