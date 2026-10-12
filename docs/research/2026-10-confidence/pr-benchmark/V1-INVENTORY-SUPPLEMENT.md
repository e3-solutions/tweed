# Retrospective inventory qualification of the first hybrid cohort

This supplement audits transport availability. It does not replace or change
registered primary grades, repair raw receipts, or rank provider accuracy. The
registered first-cohort files and every observed raw/graded receipt binding were
independently checked before this projection was generated.

All 48 planned assignments remain accounted for:

| State at interruption | Assignments |
| --- | ---: |
| Final trial receipt, independently graded | 19 |
| Assignment directory exists; no final receipt | 2 |
| No assignment directory; never started | 27 |
| Registered denominator | 48 |

An existing assignment directory establishes coordinator allocation, not a
successful provider call. The supplement also records available provider
request files and partial stage receipts. The two interrupted assignments have
no invented final completion, task grade, or cost. Twenty-seven absent
assignments remain unstarted. All 19 final receipts have independent frozen
oracle grading; original grades are retained even when this supplement declares
the harness invalid.

Across final and partial stage receipts, all 40 observed Opus initialization
inventories showed missing expected MCP tools. The `cp_trial` server failed and
only `StructuredOutput` was offered. Each of these is a supplemental harness
failure, even if a model emitted a valid terminal answer. Unknown inventories
remain unknown rather than being silently accepted. The relative-controller
startup mechanism and its no-inference RED/GREEN reproduction are documented in
[V2-PATH-QUALIFICATION.md](V2-PATH-QUALIFICATION.md).

Astra also had 17 separately recorded `PermissionError: [Errno 1] Operation not
permitted` stage errors and one recorded `OSError: [Errno 28] No space left on
device`. These are preserved as distinct operational observations. This
supplement does not attribute those errors to model accuracy or assume that the
Claude path failure explains them. Astra's available inventory evidence is its
historical offline declared-tool probe, not a live wire observation; its three
resource handlers are disclosed.

There are zero supplementally qualified verified successes. This finding means
the attempted transport was unsuitable for the desired mixed-provider
comparison; it cannot establish whether either provider is better at the tasks.
Actual available model attribution and costs are retained. Unknown costs remain
null, and no subscription quota or billing equivalence is inferred.

Reproduce the read-only projection:

```sh
python3 -B docs/research/2026-10-confidence/pr-benchmark/v1_inventory_supplement.py \
  --study .confidence/benchmark/hybrid-study-final \
  --output .confidence/benchmark/hybrid-study-final/v1-inventory-supplement.json
```

Three synthetic controls verify that classification preserves the frozen primary
rows and raw receipt bytes, that unknown costs and unstarted/interrupted states
remain explicit, and that ungraded or modified raw receipts are rejected.
Private operational output retains the detailed local file references and
stage usage; this report includes only the aggregate observations.
