# Confidence Protocol

Confidence should come from evidence, not from an agent saying it is confident.

Confidence Protocol is a small Codex plugin. It helps Codex understand the goal,
keep the code simple, test the right behavior, use independent review when risk is
high, and explain what remains uncertain.

It does not replace Codex. It makes the work easier to trust.

## Quick start

### 1. Install

In the Codex desktop app, open the **Plugins** tab. In Codex CLI, enter `/plugins`.
Install **Confidence Protocol** from your team's plugin marketplace. Start a new task
after installation so Codex loads the skill.

Requirements:

- Codex
- Python 3.10 or newer
- Git, recommended for evidence tied to a specific code state

### 2. Ask for the work normally

You do not need a long prompt. Ask for the outcome you want:

> Fix the duplicate invoice bug.

> Add team invitations.

> Research the best queue for this service.

> Build the new quoting flow.

Confidence Protocol already covers simple code, useful tests, review when needed,
clear updates, and honest uncertainty. To invoke it explicitly, say:

> Use Confidence Protocol to fix the duplicate invoice bug.

### 3. Read the final report

Codex ends with four things:

- What changed
- What evidence passed
- What was not tested
- What remains uncertain

For code changes, it also explains how to undo the work when rollback matters.

That is the normal user flow. Installed users can also ask Codex to run health and
support commands. Direct Python commands are for maintainers working from this source
repository.

## How it works

The protocol uses the lightest safe mode:

| Mode | Use it for | Proof |
| --- | --- | --- |
| Quick | Small, local, reversible work | Inspect the change and run one focused check |
| Standard | Normal bugs, features, refactors, and research | Define proof first, run focused and broader checks, review when risk calls for it |
| Critical | Security, privacy, money, destructive changes, and large product work | Add independent test design, adversarial review, real boundary tests, and rollback proof |

Most work stays with one agent. Extra reviewers are added only when the risk,
uncertainty, or failed evidence justifies them.

The main loop is simple:

1. State the goal and limits.
2. Turn important claims into proof obligations.
3. Build the smallest useful slice.
4. Run checks that could prove the work wrong.
5. Review simplicity and test quality.
6. Report what the evidence supports.

## Evidence commands

The evidence tool uses only the Python standard library. The examples below are for
maintainers and assume this repository is the current directory.

Create a task contract and report:

```sh
python3 skills/confidence-protocol/scripts/confidence.py init \
  --title "Add team invitations" \
  --mode standard \
  --task-type feature
```

Fill in `.confidence/contract.json` before implementation. Fill in
`.confidence/report.json` as evidence is collected. Empty template fields are not a
valid report.

Capture a test run:

```sh
python3 skills/confidence-protocol/scripts/confidence.py run \
  --id invitation-tests \
  --directory .confidence \
  --cwd . \
  -- python3 -m pytest tests/test_invitations.py
```

Validate work in progress:

```sh
python3 skills/confidence-protocol/scripts/confidence.py validate
```

Require complete release evidence:

```sh
python3 skills/confidence-protocol/scripts/confidence.py validate --require-complete
```

Render the readable report:

```sh
python3 skills/confidence-protocol/scripts/confidence.py render
```

Captured runs store command output, exit status, time, log hash, and Git workspace
fingerprint under `.confidence/runs/`. Supporting evidence becomes stale when the
code changes. A run stops after 30 minutes or 10 MB of output by default.

Use `diagnostic_run_ids` for expected failures, such as the failing test before a bug
fix. Use `run_ids` only for successful evidence that supports a final claim.
After each captured run, add its printed ID to the matching evidence item in
`report.json`. Run plain `validate` while collecting evidence. Run
`validate --require-complete` only after every obligation and release gate is done.

## When something goes wrong

Installed users should ask Codex:

> Run the Confidence Protocol doctor and explain any failures.

Maintainers working from this repository can run the health check directly:

```sh
python3 skills/confidence-protocol/scripts/confidence.py doctor
```

It checks:

- Plugin and CLI versions
- Python and Git
- Evidence directory permissions
- Atomic file support
- Subprocess execution and cleanup support
- Telemetry configuration
- Old Bonaparte commands still on the machine

If the cause is still unclear, ask Codex:

> Create a redacted Confidence Protocol support bundle for this repository.

Maintainers can create it directly:

```sh
python3 skills/confidence-protocol/scripts/confidence.py support-bundle
```

Send the generated `confidence-support-*.zip` to the team. It contains the doctor
result, structured events, and redacted run metadata. It excludes source code,
prompts, command arguments, command output, paths, environment values, usernames,
hostnames, and raw logs.

Command failures after argument parsing print a diagnostic operation ID. Use that ID
to match the failure to `.confidence/telemetry/events.jsonl` or the support bundle.

## Team telemetry

Remote telemetry is off by default. To send safe events to your own collector, set:

```sh
export CONFIDENCE_TELEMETRY_ENDPOINT="https://telemetry.example.com/confidence"
export CONFIDENCE_TELEMETRY_TOKEN="your-token"
```

Keep the token in the environment. Do not place it in command arguments or commit it.

Test the connection:

```sh
python3 skills/confidence-protocol/scripts/confidence.py doctor --probe-telemetry
```

After recording a command completion or crash event locally, the plugin attempts one
JSON POST with a one-second timeout. Delivery is best effort. It cannot change the
coding command's result. Failed events are not retried, so the plugin cannot build an
unbounded queue.

Remote events contain only:

- Schema, plugin, Python, and platform versions
- Random installation, event, and operation IDs
- Event type and timestamp
- Command name, status, stable error code, and coarse duration

The installation ID is stable for one local evidence directory, so remote events are
not anonymous. The payload contains no username, hostname, or explicit personal
identifier. Your collector can still observe normal network metadata such as source
IP.

## Local data and privacy

- Test logs can contain secrets printed by the tests. Do not share raw logs.
- The redacted support bundle is the safe support path. Review it before sharing.
- Local structured events are capped at 1 MB. New events are dropped at the limit.
- Set `CONFIDENCE_DISABLE_DIAGNOSTICS=1` to disable local diagnostics.
- Delete `.confidence/telemetry/` to remove local events and the installation ID.
- Remove the telemetry environment variables to stop remote export immediately.

## Moving from old Tweed

Version 0.4 replaces the old Tweed and Bonaparte product. Installing this plugin does
not delete an older `bonaparte` command. Run `doctor` to detect one, then remove it
after confirming your team no longer needs it.

## Develop and release

Run the test suite:

```sh
python3 -m unittest discover -s skills/confidence-protocol/tests -v
```

Build a clean plugin archive from a committed tree:

```sh
git archive --format=zip --prefix=confidence-protocol/ \
  --output ../confidence-protocol-plugin.zip HEAD
```

Repository tests, local evidence, editor files, and bytecode are excluded from the
release archive.

See [CHANGELOG.md](CHANGELOG.md) for release history.
