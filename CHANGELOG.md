# Changelog

This file records user-visible changes to Tweed and Confidence Protocol.

## Unreleased — agent evidence workflow

- Capture source content before and after commands, including tracked files hidden
  by Git's assume-unchanged or skip-worktree flags. Reject ambiguous routing,
  unenumerated nested repositories, and unsupported submodules for code proof.
- Reuse fingerprints within validation and perform a fresh final check for drift.
- Avoid false staleness from concurrent atomic evidence publication, with narrow
  output-name exclusions and one bounded inventory retry.
- Add compact `run --json` receipts while retaining complete logs and hashes.
- Add explicit, atomic `record` updates with cooperating-writer locking and
  structured errors. Reject non-regular JSON document inputs without blocking.
- Coordinate initialization with report writers; add preserving `init --resume`
  recovery for interrupted contract-only setup and refuse ambiguous existing pairs.
  Reset removes the old report first; file replacements are individually atomic.
- Reject non-regular or symlink captured logs without blocking evidence readers.
- Preserve partial and research observations without claiming current-code proof.
- Clean up captured process groups on SIGINT/SIGTERM, including repeated signals.
- Reject non-finite timeouts before execution and preserve command results when
  optional Git provenance is unavailable.
- Label illustrative shipped evidence as partial and describe validation success
  as completed evidence checks, rather than certifying release readiness.

Compatibility: old Git-diff bindings require recapture for current-code completion;
tracked reports can stale prior evidence; `init` and `record` require Unix directory locking.
Git-enumerated regular files and symlinks define fingerprint scope. Ignored
dependencies, untracked special files, external services, and transient
change-and-revert are not certified. Reserved untracked output names must not hold
source inputs.

## [0.4.0] - 2026-08-28

Version 0.4.0 replaces the old Tweed and Bonaparte product with Confidence Protocol.

### Added

- A Codex-native workflow for clear goals, proof obligations, simple code, focused
  tests, risk-based review, and honest final reports.
- Quick, Standard, and Critical modes.
- Local evidence contracts, captured test runs, log hashes, Git workspace binding,
  release validation, and Markdown reports.
- Structured local diagnostic events with stable error codes and operation IDs.
- A `doctor` command for installation, runner, filesystem, cleanup support, legacy
  install, and telemetry checks.
- A redacted `support-bundle` command for team troubleshooting.
- Optional HTTPS telemetry with a fixed private schema and one-second timeout.
- CI across Python 3.10, 3.12, and 3.14.
- Privacy and failure-isolation regressions for real child commands.

### Changed

- Codex remains the main harness. The plugin adds proof and review only where the
  task's risk requires them.
- Independent reviewers now attack specific decision boundaries instead of running
  on every task.
- Child exit `125` is reported separately from a runner failure.
- Telemetry and local logging cannot replace the underlying command result.

### Removed

- Bonaparte runtime and launchers.
- Linear-backed workflow orchestration.
- Autoresearch commands and prompts.
- The old Tweed installation script and test suite.

### Privacy

- Remote telemetry is disabled by default.
- Remote events exclude source, prompts, arguments, output, paths, environment
  values, usernames, hostnames, and raw exceptions.
- Support bundles exclude raw logs and other work content.

### Migration

Installing Confidence Protocol does not remove an old `bonaparte` command. Run
`doctor` to detect it, then remove it after confirming the old tool is no longer
needed.

[0.4.0]: https://github.com/e3-solutions/tweed/compare/v0.3.0...v0.4.0
