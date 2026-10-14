# Independent first-cell grade-invocation correction review

The independent grader invocation failed because the driver received a relative --study argument and passed its relative captured-source path to a subprocess whose cwd was fair-loop. That child resolved a nonexistent nested directory. The actual captured directory exists at its absolute path. The original exit-2 unknown grade and captured_grade_source_bound=false receipt remain valid historical records of this operator invocation error.

Independently checked the retained source: raw tree SHA29313ab1352993ab7a22176cdd7943070c99f11867814376f82eb470195a6a1c equals both the original expected captured-source hash and after receipt; current full inventory equals the stable stage snapshot and policy is unchanged. Raw provider stream reparses to observed claude-opus-5-5, success terminal, exit0, no timeout/anomalies, and owned group absent. Stream output hash and current frozen registration verify.

**PASS to correct only the frozen independent grade invocation:** supply that exact absolute captured source path and retain new raw output/receipt in a separate diagnostic directory. Keep source, provider receipt, grading criteria and registration unchanged; no provider retry or actor repair is justified by this path error. All later invocations must pass absolute --study. Corrected product proof still needs to bind the same captured source and actual grader outputs before any result or continuation is declared qualified.

My prelaunch review did not catch this caller/cwd path mismatch. The passing prepare/prefix checks did not establish that a relative execute invocation would reach the grader correctly. Preserve this correction alongside the readiness review; do not silently rewrite the initial unknown as a product failure or discard it.

Current reviewed bindings (SHA256):
- main.receipt.json: `0e9a04e03427bffacd8d6341dbb01678a3d324dd2dfbb8bfe85253226d9f1694`
- after/receipt.json: `77c5f50bc7a12b3e61908837dd826c060d615dc709ba407475315dc2f46cb8fa`
- evaluation/receipt.json: `86693c749dca6206ab80170c53c326248e25b67d5ab3bdb0994d78f9e2dcc80b`
- evaluation/grader.stdout: `1902ebed8b51cf24dada1243f9fefa1e2e9a6ae64c16667d7f771aba542e4160`
- evaluation/grader.stderr: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

No model calls, source/grader edits or grader executions were performed by this reviewer. This review authorizes no additional study cells or changes to promotion criteria.
