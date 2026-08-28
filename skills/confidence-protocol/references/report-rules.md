# Confidence report rules

The report is a map from claims to evidence. It is not a work diary.

## Required content

- Exact goal and mode.
- Important assumptions.
- Each proof obligation.
- Evidence for each obligation.
- Captured test commands and results.
- Simplicity review.
- Open risks and untested areas.
- Rollback steps when a change was made.

## Evidence status

- `pass`: the stated evidence supports the claim in its stated scope.
- `partial`: some useful evidence exists, but a named gap remains.
- `fail`: evidence rejects the claim.
- `not_run`: the planned check was not run.

Do not turn `partial` into `pass` because the remaining gap seems unlikely.

## Captured runs

Use `confidence.py run` for deterministic checks. The runner records command arguments, timestamps, exit status, output, and a SHA-256 log digest.

Every `pass` evidence item must reference at least one captured run that exited with zero. Validation resolves each run ID and recomputes its log hash. A hash match proves that the stored output did not drift after capture. It does not prove that the chosen command was sufficient.

The hash is not a security signature. Anyone who can replace both the log and its record can forge it. The protocol protects against accidental drift and unsupported self-reporting, not a malicious writer with full access to the evidence directory.

For bugs, prefer two runs bound to the same obligation:

- Before the fix: the regression test exposes the bug with a nonzero exit.
- After the fix: the same regression test passes.

Do not put secrets in command arguments. Review captured logs before sharing them.

## Completion rule

The task can be called complete only when:

- Every required obligation has `pass` status.
- Required tests have successful captured runs.
- No open risk violates a must-not-happen rule.
- The simplicity and test-quality gates passed.
- Any required user decision was made.

Otherwise, say the work is partial, blocked, or failed. Explain the next concrete step.

## User communication

Keep updates short.

Update the user when:

- The contract is ready.
- Evidence changes the plan.
- A real choice needs the user.
- A major proof point passes or fails.
- The final report is ready.

Do not stream every internal action. The user should understand the state without managing the agent.
