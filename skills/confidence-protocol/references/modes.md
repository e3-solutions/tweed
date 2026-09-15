# Modes

Choose the lightest mode that can catch the likely failure.

## Quick

Use Quick when the task is clear, local, reversible, and low risk.

Examples:

- Rename a private variable.
- Fix a typo.
- Adjust one narrow test.
- Explain existing code.

Required proof:

- Inspect the affected code.
- Run the smallest relevant check.
- Report any check that was not run.

Subagents are usually wasteful here.

## Standard

Use Standard for normal bugs, features, refactors, and research that guides implementation.

Examples:

- Fix a production bug with a known symptom.
- Add a user-facing feature.
- Change a public API.
- Refactor a module with several callers.

Required proof:

- Write the contract and proof obligations first.
- Apply the review gate in `SKILL.md`.
- If the gate triggers, get one narrow independent review. Otherwise stay with one agent and record why review was skipped.
- Run focused tests and the relevant broader suite.
- Check simplicity and test quality.
- Record unknowns and rollback steps.

## Critical

Use Critical when failure can cause major harm or when the change is broad and hard to reverse.

Examples:

- Authentication or authorization.
- Money, billing, or quotas.
- Privacy or sensitive data.
- Destructive migration.
- Security boundary.
- A new product suite with several services.

Required proof:

- Do everything in Standard.
- Use separate proof design and adversarial review roles when subagents are available. Keep each role narrow.
- Test failure paths and rollback.
- Test the real integration boundary.
- Use existing authorization; request the user's decision only for an unresolved consequential choice or an action needing additional authorization.
- Prefer staged release, feature flags, or a dry run when the system supports them.

## Raise the mode when

- The goal is unclear.
- The code has weak tests.
- The change crosses service or data boundaries.
- The failure is hard to detect.
- The rollback is slow or destructive.
- The agent cannot observe the real environment.

## Lower the mode only when

New evidence removes the risk. Convenience is not evidence.
