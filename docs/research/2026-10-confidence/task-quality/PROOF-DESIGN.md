# Prospective task-quality proof design

Independent native Codex note, written before the requested Opus guidance refinement.
Scope: guidance-only unreleased 0.8.1; core, schemas, version, old benchmark records and installed 0.8 stay unchanged.
No model calls, new harness/code, broad tests or observed solving results belong to this design.
Actual model/runtime metadata is unobserved; requested model names cannot establish who ran or what succeeded.
Manual case design/calibration checks evaluator logic, not measured solving efficacy, reliability or speed improvement.

## Small completion heuristics to inspect in the guidance

- Next action: recover supplied decisions; resolve only necessary consequential unknowns; defer optional preferences visibly.
- Finish: pair each REQUIRED accepted behavior with current observed proof; missing required proof stays unfinished.
- Fix: reproduce the failure, locate its causal boundary, and verify both the repaired trigger and important neighboring behavior.
- Tools/data: choose the narrowest available authorized interface that exposes the required authority, freshness and semantics.
- Tests: assert observable outputs or state transitions; retain the real boundary being claimed; avoid implementation names and copied assertions.
- Economy: stop discovery when the next authorized action is ready; reuse sufficient current evidence; expand checks only for a reason.
- Report: separate delivered behavior, remaining required work, explicit exclusions and uncertain execution attribution.
These are decision checks, not a new universal ledger, mandatory test count, MCP quota or model ceremony.

## Three small manual task cases

### A. Ambiguous intent with a recoverable decision (newly authored paper case)

Request: “Add export for the current report.” Supplied product decision says current means the visible filtered rows in displayed order.
The supplied data includes a filtered-out row, two visible rows and a visible label containing a comma/quote.
Encoding and filename styling are optional preferences; the requested outcome does not include publishing or sending the export.
Expected intake: use the existing current-report decision, identify the export boundary, and proceed without asking it again.
If that decision is removed in a control, ask only the consequential visible-versus-all-rows question; continue independent preparation.
Expected behavior checks: exported rows match visible filter/order, excluded rows remain excluded, and quoted fields round-trip correctly.
Expected completion: current executed round-trip/filter checks cover the requested export; optional filename styling can be deferred.
An implementation that exposes the same correct export through another suitable component passes; a verbal “done” without proof does not.

### B. Authentic defect and a causal repair (existing historical PR37 calibration case)

Use the already pinned Tweed PR37 base/accepted behavior as an authentic example, not a new defect or fresh benchmark task.
Failure: a queued app-server item/started notification after steer acknowledgement falsely rejects a compliant soft-budget wrap-up.
Expected diagnosis: receipt validity owns completion; notification arrival order alone cannot establish new root work.
Expected checks: queued activity plus a valid needs-input continuation succeeds; invalid state/question/summary remains rejected.
Also preserve one budget steer, the bound resume session, and provider exit/reap on successful completion.
The existing independent queued owner cases provide the behavior examples; do not rerun or revise historical scores for this note.
A repair at any correct causal boundary passes. Removing all wrap-up validation fails the negative controls despite fixing the positive case.
Expected completion: distinguish author repair checks from independent checks and rerun proof affected by the final source change.

### C. Multiple tool/data boundaries (newly authored offline paper case)

Request: “Total yesterday’s settled USD sales for account X in Toronto time, with traceable source records.” Read-only authority only.
Available fixtures represent a paginated order service and an invoice service; a cached CSV has an older timestamp and different totals.
Orders identify the account and sales window; invoices own settlement state, currency and integer minor-unit amounts.
Pages contain orders A,B then duplicate B,C. Authoritative settled invoices are A=1250 USD cents and B=800 USD cents.
C is pending EUR; an unrelated account record is present. The time fixture supplies the explicit Toronto interval and boundary records.
Expected tool use: follow necessary pagination, join stable order/invoice IDs, respect authoritative units/status/time and deduplicate.
Expected behavior checks: total is USD 20.50 from A+B once; C, unrelated accounts and out-of-window records are excluded.
Expected evidence: retain record IDs, relevant source timestamps and the exact interval; do not present the cached CSV as current authority.
Equivalent valid API/MCP/CLI interfaces pass if they preserve these boundaries; no points for MCP names, calls or connector count.
An unavailable required data boundary stays a concrete gap; cached or partial data may support a labeled partial answer only.
No live connector is invoked or claimed verified by this design; offline fixtures cannot establish actual service behavior.

## Evaluator controls, applied manually before any efficacy claim

| Control | Expected classification |
|---|---|
| Wrong repair accepts every wrap-up, including malformed receipts | Product behavior failure: required negative case fails. |
| Export is correct but its required filter/round-trip evidence is absent | Required proof gap; completion remains unsupported. |
| Offline cases pass; report says live providers were excluded by the accepted contract | Valid scoped result plus caveat, not an unfinished required live check. |
| Tool setup times out before the first product action; logs show adapter/bootstrap stall | Setup failure/unknown product outcome; not an automatic protocol failure or pass. |
| Command times out and receipts cannot distinguish setup, provider, cleanup or product delay | Unknown attribution; preserve logs/stage timings, avoid assigning blame. |
| A required API response must arrive within 200ms; measured product boundary takes 350ms | Required latency failure even if the harness eventually returns successfully. |
| Equivalent implementation changes helper names/config formatting but behavior stays correct | Same acceptance; no keyword, source-shape or MCP-count grading. |

## Timeout attribution and economy

Record the timed stage, deadline owner, whether product execution began, cleanup result and actual returned evidence where available.
A suspected harness problem needs supporting setup/control evidence; suspicion alone does not absolve product or protocol behavior.
A bounded diagnostic or justified infrastructure retry may clarify attribution; retain the first result and never count silence as success.
Do not convert every slow run into a software failure: product latency matters only where the accepted task requires it.
Evaluate waste by avoidable duplicate reads/checks, unneeded delegation and irrelevant scope expansion in context, not raw elapsed time alone.
Necessary pagination, verification and slow external dependencies are not waste merely because they increase call count or duration.
This note supports reviewing guidance and calibrating a few counterexamples; measured solving efficacy needs a separately authorized study.
