---
name: confidence-protocol
description: Build, fix, refactor, research, or review software with justified confidence. Use when a user asks for reliable implementation, simple code, clean tests, full product work, adversarial review, proof that a change works, or the Confidence Protocol by name.
---

# Confidence Protocol

Earn confidence with evidence. Do not use confident language as a substitute for proof.

Use Codex as the main harness. Add only the checks that match the task's risk. Keep the process visible and easy to understand.

## Start with the contract

Before changing code, state:

- Goal: the user outcome.
- Must happen: observable success conditions.
- Must not happen: regressions, unsafe states, and scope limits.
- Constraints: technical, product, time, and compatibility limits.
- Non-goals: work that is outside this task.
- Open questions: facts that could change the solution.

Resolve facts from the codebase when possible. Ask the user only when a choice is important and cannot be discovered safely.

Before naming assumptions, trace each user-visible label, permission, or result through every validation and execution gate to the code predicate that enables the action. Try one contradiction: keep the raw prerequisite present while making the next validator reject it. If the label or permission still promises the action, the predicate is incomplete. Reuse a predicate that includes every gate, or keep it as an open question so the review gate triggers.

Tell the user the selected mode and the main proof plan in one short update.

## Choose a mode

Read [modes.md](references/modes.md). Use the lightest safe mode.

- Quick for small, clear, reversible work.
- Standard for normal bugs and features.
- Critical for security, privacy, money, destructive data changes, major migrations, or broad product work.

Never lower a mode to save time without telling the user what proof will be lost.

## Choose the task profile

Read [task-profiles.md](references/task-profiles.md). Pick the closest profile. A task may combine profiles.

Turn each important claim into a proof obligation before implementation. State what evidence would support or reject it.

For Standard and Critical work, use the local evidence files when writing to the repository is in scope:

```sh
python3 <plugin-root>/skills/confidence-protocol/scripts/confidence.py init \
  --title "<task title>" \
  --mode <standard-or-critical> \
  --task-type <research|bug|feature|refactor|product|security>
```

If the plugin root is not known, find this `SKILL.md` and resolve the script relative to it. Do not create evidence files for a read-only request unless the user asks for them.

## Separate proposal from proof

The implementer does not get to invent all tests after seeing its own solution.

Use one agent by default. After writing the contract, run this review gate once. Independent review is required when any of these are true:

- The task is Critical.
- An open question could change the solution.
- The change crosses an authorization, data, service, SQL, or external-system boundary.
- Focused proof fails unexpectedly or the implementation grows beyond the stated scope.
- A failure would be hard to detect or rollback would be slow or unsafe.

If none apply, continue without a reviewer and state the reason in the final report. Do not add reviewers merely because subagents are available.

For Standard work that triggers the gate, use one independent read-only review. Give it only the contract, diff, focused test results, and one narrow question. Choose the review that attacks the largest risk:

- Test designer: defines failures and end-to-end proof before seeing implementation details.
- Critic: finds counterexamples, hidden assumptions, and simpler designs.
- Integration reviewer: checks boundaries and real user flows.

Use one review pass. Run another only if the first review causes a material change to the decision boundary. For Critical work, use separate test-design and adversarial-review roles when subagents are available. Add a domain or security reviewer only when the risk calls for it.

For Critical work, let the independent test designer add proof obligations before implementation. Do not remove those obligations without telling the user why.

Give each reviewer a narrow question and the raw facts it needs. Ask for evidence and a concrete counterexample. Do not ask several agents the same broad question and vote on their answers.

Give the reviewer the highest-risk decision boundary and ask for a concrete input or state that could land on the wrong side of it.

Models propose. Tools decide. Prefer source inspection, compiler output, tests, runtime traces, logs, database checks, and browser evidence over model agreement.

Do not call an external model unless the user approved the cost and the data exposure. Treat external model agreement as review input, not proof.

## Build in proof-sized slices

Implement the smallest vertical slice that can produce useful evidence.

After each slice:

1. Run the narrow deterministic checks.
2. Inspect failures before adding more code.
3. Update assumptions when evidence changes them.
4. Tell the user only about meaningful progress, changed scope, or a decision they must make.

Do not hide a failed check. Do not replace a relevant failing test with an easier test.

For a bug, capture the regression test before the fix and after the fix. The first run should expose the bug. Record it in `diagnostic_run_ids`. The second should pass and belongs in `run_ids`. This is the preferred fail-then-pass proof. Do not automate Git reverts in a dirty repository.

## Gate simplicity

Simplicity is a release condition. It is not a style preference.

Before calling the work done, ask:

- Can any new layer, type, option, or dependency be removed?
- Does each abstraction solve a present need?
- Is there one clear owner for each rule?
- Does the code follow the repository's existing shape?
- Can a new maintainer trace the main path without agent reasoning?
- Is the change smaller than the problem it solves?

Delete unused scaffolding. Prefer direct code until repeated variation proves that an abstraction is needed.

## Gate test quality

Tests must be simple evidence.

Before writing tests, name each important decision rule that changes the outcome. Use the smallest set of cases that could disprove each rule. Test both sides or an exact edge when that boundary changes user-visible or safety behavior. When a label describes an action, keep its prerequisite present but invalid and prove the label does not promise an action that validation blocks. Include other partial, malformed, or stale states only when they are realistic. If the same rule controls several consumers, such as a displayed label and whether an action can run, prove that they stay aligned. Do not multiply cases mechanically.

- Test public behavior and important boundaries.
- Use unit tests for local logic.
- Use integration tests for component contracts.
- Use end-to-end tests for the few critical user paths.
- Keep setup small and names literal.
- Avoid duplicate cases that prove the same claim.
- Avoid mocks that remove the behavior under test.
- Make failures explain the broken promise.

When a claim depends on SQL, a migration, or an external service contract, mocks prove only local wiring. Run the real boundary or mark the evidence partial and name the missing check.

Tests that are hard to read lower confidence even when they pass.

## Finish with a confidence report

Read [report-rules.md](references/report-rules.md).

For Standard and Critical work, record evidence against every proof obligation. Validate the files:

```sh
python3 <plugin-root>/skills/confidence-protocol/scripts/confidence.py run \
  --id <clear-run-id> \
  --directory .confidence \
  --cwd <project-root> \
  -- <test-command> <arguments>
python3 <plugin-root>/skills/confidence-protocol/scripts/confidence.py validate \
  --require-complete
python3 <plugin-root>/skills/confidence-protocol/scripts/confidence.py render
```

Add successful supporting runs to the matching evidence item's `run_ids` list in `report.json`. Every supporting run for a `pass` claim must succeed. Put expected pre-fix failures and other diagnostic runs in `diagnostic_run_ids`; they never turn a claim into a pass. The validator checks every referenced record and recomputes its log hash. The completion check also rejects partial proof, failed or unrun required tests, and failed simplicity gates. Use plain `validate` only while work is still in progress.

The runner does not use a shell. Put `--` before the executable and arguments so command options cannot be confused with runner options. Never put secrets in command arguments. Captured logs can also contain secrets printed by tests, so review them before sharing or committing them.

A runner error exits with code 125 and creates no JSON record. A tested command may also return 125, but then its JSON record exists. The stored log hash detects later drift. It is not a signature against someone who can rewrite both the log and record.

Every CLI command also writes a small structured event to
`.confidence/telemetry/events.jsonl`. If a user reports a diagnostic operation ID or
the tool itself fails, run `confidence.py doctor` first. If the cause is still not
clear, create a redacted file with `confidence.py support-bundle`. Do not ask the
user to share raw run logs. Remote telemetry is off unless the team configures its
own HTTPS endpoint. Telemetry failure never changes the coding command's result.

The final user response must say:

- What changed or what was learned.
- What evidence passed.
- What was not tested.
- What remains uncertain.
- How to undo the change when rollback matters.

Use calibrated words:

- Proven: directly supported by deterministic evidence in the stated scope.
- Supported: good evidence exists, but important uncertainty remains.
- Unknown: not checked or not observable.
- Failed: evidence rejects the claim.

Never say the whole system is proven. State the exact scope of the evidence.
