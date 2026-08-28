# Changelog

This file records user-visible changes to Tweed and Confidence Protocol.

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
