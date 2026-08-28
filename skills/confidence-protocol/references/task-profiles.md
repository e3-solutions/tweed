# Task profiles

Use these profiles to choose proof. Do not apply one test recipe to every task.

## Research

Claims:

- The sources are current and relevant.
- Facts are separate from inference.
- The answer covers the user's real decision.

Evidence:

- Primary sources.
- Direct links or code references.
- Competing explanations.
- Clear unknowns.

## Bug

Claims:

- The stated cause produces the symptom.
- The fix removes the cause.
- The fix does not break nearby behavior.

Evidence:

- Reproduction before the fix.
- A regression test that fails before and passes after.
- Focused tests around the boundary.
- Runtime evidence when the bug depends on real integration.

## Feature

Claims:

- The user can complete the intended flow.
- Invalid states fail safely.
- Existing behavior still works.

Evidence:

- Acceptance tests from user behavior.
- Unit tests for important rules.
- Integration tests at changed boundaries.
- One end-to-end test for the critical path.

## Refactor

Claims:

- Public behavior did not change.
- The new shape is simpler or removes a real constraint.
- Callers still work.

Evidence:

- Characterization tests before the change.
- Existing suite before and after.
- A smaller dependency or complexity surface.
- No unused compatibility layer.

## Product

Claims:

- The main user journey works across parts.
- Data and permissions stay consistent.
- Partial failure has a safe outcome.
- The product can be operated and rolled back.

Evidence:

- A thin vertical slice first.
- Contract tests between services.
- End-to-end tests for key journeys.
- Migration, observability, and rollback checks.
- Explicit decisions at product boundaries.

## Security

Claims:

- The threat is stated correctly.
- Controls exist at the real trust boundary.
- Bypass and failure paths are covered.
- Sensitive data is handled as promised.

Evidence:

- Threat model.
- Negative tests and abuse cases.
- Authorization checks at the server boundary.
- Dependency and configuration checks.
- Independent security review.
