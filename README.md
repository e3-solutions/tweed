# Confidence Protocol

Confidence should come from evidence, not from an agent saying it is confident.

This Codex plugin adds a small workflow on top of the tools Codex already has. It does not replace Codex. It helps Codex state the goal, plan the proof, use independent review where it matters, keep the code simple, and report what the evidence supports.

## What it adds

- A clear contract before code changes.
- A source-of-truth check that keeps labels, permissions, and actions on the same rule.
- Proof obligations chosen before implementation.
- Quick, Standard, and Critical modes.
- A small review gate that keeps ordinary work single-agent.
- Narrow independent review when risk or failed proof justifies it.
- Separate checks for code quality and test quality.
- Captured test runs with exit codes and drift-checked logs.
- A clear final report with open risks and rollback steps.
- A local structured event log for failures inside the tool.
- A `doctor` command for installation and telemetry checks.
- A redacted support bundle that is safe to share with the team.
- Optional remote telemetry with a fixed, private data shape.

## What it does not add

- A new coding harness.
- A required external service.
- Automatic calls to another model.
- A claim that passing tests prove everything.
- A dashboard or telemetry collector.

Codex can use its built-in subagents. An external model can be added later for high-risk review. That should require user approval because code may leave the local environment.

## Use it

Ask Codex:

> Use the Confidence Protocol to add team invitations. Keep the design simple and prove the full user flow.

For most work, the workflow stays with one agent. It adds independent review only when scope is unclear, a real system boundary changes, proof fails, or the impact is high.

## Evidence files

For Standard and Critical work, the skill can create `.confidence/contract.json` and `.confidence/report.json` in the project.

Create them:

```sh
python3 skills/confidence-protocol/scripts/confidence.py init \
  --title "Add team invitations" \
  --mode standard \
  --task-type feature
```

Validate work in progress:

```sh
python3 skills/confidence-protocol/scripts/confidence.py validate
```

Before release, require every proof obligation and release gate to pass:

```sh
python3 skills/confidence-protocol/scripts/confidence.py validate --require-complete
```

Report schema 3 records the review-gate decision, reason, roles, and findings. Critical completion requires separate test-design and adversarial-review roles. Standard work records why review ran or why the gate stayed closed.

Capture a test run:

```sh
python3 skills/confidence-protocol/scripts/confidence.py run \
  --id invitation-tests \
  --directory .confidence \
  --cwd . \
  -- python3 -m pytest tests/test_invitations.py
```

The command runs without a shell. Its output still appears in the terminal. The plugin stores the command arguments, resolved executable, start and end times, exit code, log, and log hash under `.confidence/runs/`. In a Git project, it also records the current commit and working-tree fingerprint. A supporting run becomes stale when the source changes. Expected pre-fix runs may be stale because they belong in `diagnostic_run_ids`, not `run_ids`.

Runs stop after 30 minutes or 10 MB of output by default. Use `--timeout-seconds` or `--max-log-bytes` before `--` when a focused check needs a different bound. A timeout is recorded with exit code 124. A log limit is recorded with exit code 122.

Add the printed run ID to the matching evidence item in `report.json`. A claim cannot have `pass` status unless it references a captured run that exited successfully. Validation also recomputes each log hash.

Render a readable report:

```sh
python3 skills/confidence-protocol/scripts/confidence.py render
```

The script uses only the Python standard library.

Captured logs may contain secrets printed by tests and absolute local paths. Review them before sharing. In shared repositories, consider ignoring `.confidence/runs/` while keeping the contract and final report.

The hash detects a log changed after capture. It is not a security signature because the record and hash are stored together. A tool error exits with code 125 and writes no JSON record. A child stopped by a signal keeps the negative signal code in its record and returns the usual `128 + signal` process status.

The atomic record write needs a local filesystem that supports hard links. This matches the plugin's intended local use.

## Diagnose a problem

Every command writes small structured events to `.confidence/telemetry/events.jsonl`.
The file records the tool version, operation ID, command, result, stable error code,
coarse duration, Python version, and platform. It never records source code, prompts,
command arguments, command output, paths, environment values, usernames, or hostnames.

Check an installation:

```sh
python3 skills/confidence-protocol/scripts/confidence.py doctor
```

The doctor checks the plugin version, Python, evidence directory, atomic writes,
subprocess execution, Git, process cleanup, old Bonaparte commands, and telemetry
configuration. It does not use the network unless you add `--probe-telemetry`.

Create a support file:

```sh
python3 skills/confidence-protocol/scripts/confidence.py support-bundle
```

The ZIP contains the doctor report, safe events, and redacted run metadata. It does
not contain logs, arguments, output, source, prompts, paths, or environment values.
Review the bundle before sharing it, as you would any support file.

Local diagnostics are limited to 1 MB. When the limit is reached, new events are
dropped. Set `CONFIDENCE_DISABLE_DIAGNOSTICS=1` to turn local diagnostics off.
Delete `.confidence/telemetry/` to remove the local history and installation ID.

## Optional team telemetry

Remote telemetry is off by default. To send the same safe event shape to your own
collector, set:

```sh
export CONFIDENCE_TELEMETRY_ENDPOINT="https://telemetry.example.com/confidence"
export CONFIDENCE_TELEMETRY_TOKEN="your-token"
```

Keep the token in the environment. Do not put it in command arguments or commit it.
The endpoint must use HTTPS. Plain HTTP is allowed only for a loopback test server.
Credentials, query text, and fragments are rejected in endpoint URLs.

Each completed command sends one JSON POST with a one-second timeout. Delivery is
best effort. A telemetry failure is recorded locally and never changes the command's
exit code. Events are not retried, so the tool cannot build an unbounded queue.
Use `doctor --probe-telemetry` to send one safe health event.

Remote fields are limited to:

- Schema, tool, Python, and platform versions
- Random installation, event, and operation IDs
- Command name, status, stable error code, and coarse duration

The stable installation ID means remote events are not anonymous. It identifies one
local evidence directory. It does not identify a person or machine.

This repository replaces the old Tweed and Bonaparte product. Installing the plugin
does not remove an older `bonaparte` command from a developer's machine. `doctor`
warns when it finds one. Remove the old installation after confirming nobody still
needs it.

## Install

Add this plugin folder to a Codex plugin marketplace. Then install it through the Codex plugin browser and start a new task. Codex CLI users can open the browser with `/plugins`.

## Build a clean archive

The source is a Git repository. Build releases from a committed tree so editor files, bytecode, local evidence, and other untracked state cannot enter the package:

```sh
git archive --format=zip --prefix=confidence-protocol/ \
  --output ../confidence-protocol-plugin.zip HEAD
```

The export rules exclude repository-only files and `.confidence/`. Validate the extracted archive with the Codex plugin and skill validators before sharing it.

## Design choice

Version 0.4 is one skill plus one local evidence tool. It uses the mature parts of Codex instead of copying them. Its review gate protects the fast path instead of adding reviewers to every normal task. Its release check separates valid evidence files from complete evidence. Optional telemetry is a small HTTPS event export, not a new harness, daemon, or MCP server.
