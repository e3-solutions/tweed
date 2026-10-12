# Closed-study analysis controls

The new [V2 analyzer](analyze_hybrid_v2.py) was developed during the frozen study,
without reading its live task outcomes. It preserves the registered fixed-main
comparisons and scoring definitions. It changes no model prompt, trial, task oracle,
normalized grade, protocol or governing input. Original84 and V148 remain separate.

An independent reviewer reproduced three publication errors in the first version:

1. Twelve permanently ineligible assignments with diagnostic passing oracle values
   produced verified-acceptance bounds from0to12. The repaired bound fixes their
   verified contribution at zero. Missing receipts with unknown eligibility and
   otherwise eligible unknown acceptance remain distinct unknown possibilities.
   Valid-only complete-case sensitivities still exclude ineligible assignments;
   fixing their verified score at zero does not turn them into observed oracle failures.
2. Oracle stdout/stderr bytes could change after closure while their recorded hashes
   and all other audit bindings stayed unchanged. The analyzer now rechecks those
   regular files against their recorded digests. A known oracle verdict requires
   both bound outputs; unbound unknown diagnostics cannot supply oracle proof.
3. Two copies of a merged audit at different paths satisfied the nominal two-audit
   check. Final analysis now requires distinct role-specific records and observer
   source/registration bindings, plus current material seals. This checks declared
   provenance consistency; it does not authenticate the producer or guarantee
   independent reasoning.

The initial review is retained unchanged. A new source-bound correction receipt
records16 independently authored synthetic controls passing, including invalid
fixed-zero bounds, unknown valid/missing bounds, changed/deleted/symlinked oracle
logs, omitted known-output hashes, duplicate/merged audit contents and missing
observer/commit provenance. The reviewer also reran all48 analyzer tests and checked
paired reversals and exact46,656-resample task bootstrap against a separate reference.
These are synthetic controls, not additional model trials. Safe facts and hashes
are in [ANALYSIS-CONTROLS.json](ANALYSIS-CONTROLS.json).

The owner subsequently ran the complete current benchmark suite: **209 tests passed**
on local Python3.14.7/macOS in17.971s. These are separate from the246 core CI tests.
The launch, lifecycle, source projection and publication controls retain their
qualified boundaries; no repeated hypothesis test or posthoc task rescore occurred.

Production analysis requires the exact48 scheduled identities, the published V2
seal, unchanged governing hashes, both passing final observers, closure inventory,
raw and graded receipts, oracle output hashes and durable material bindings. It
refuses a live partial array, input overwrite and output inside the sealed study.
The six independent historical task clusters determine bootstrap units; two repeats
do not create twelve independent tasks. Acceptance, strict declared completion,
assigned peer-role closure and proof-packet quality remain distinct judgments.
Missing dollar cost stays null; partial known stage subtotals do not become totals
or subscription billing. No improvement ranking is inferred from these controls.

Use the CLI documented in the analyzer only after both final audit receipts exist.
The research analyzer/tests are omitted from the plugin release. The installed
proof CLI and frozen grading adapter are unchanged by this publication utility.
