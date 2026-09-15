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
- Git with a supported working tree for evidence that supports current-code claims
- Unix directory locking for `init` and `record` authoring commands

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

If initialization was interrupted after creating the contract, resume without
replacing the authored contract:

```sh
python3 skills/confidence-protocol/scripts/confidence.py init --resume
```

A supported existing contract is authoritative: resume creates only its missing
report, or preserves an existing pair with matching task identity and obligation
IDs. It refuses ambiguous, conflicting, or report-only states. Resume does not
validate completion. Use `--force` only for an intentional reset: it removes the
old report before replacing the contract and can leave a recoverable contract-only
state if interrupted. Each file is replaced atomically; the pair is not a single
transaction, and power-loss durability is not guaranteed.

Capture a test run. This invitation example is illustrative; replace the command
with a test that exists in your project:

```sh
python3 skills/confidence-protocol/scripts/confidence.py run \
  --json \
  --id invitation-tests \
  --directory .confidence \
  --cwd . \
  -- python3 -m pytest tests/test_invitations.py
```

The JSON receipt contains the run ID, exit status, log and record paths, and source
binding status. The full output remains in the captured log. Omit `--json` to replay
that output in the terminal. A runner failure exits with status 125 and may leave
no receipt or run record; inspect stderr before retrying with a new run ID.

Attach your explicit assessment to a contract obligation:

```sh
python3 skills/confidence-protocol/scripts/confidence.py record \
  --obligation P1 --status pass \
  --details "The invitation authorization checks support this obligation." \
  --run invitation-tests
```

`record` validates the selected result before an atomic report update. It does not
infer that a successful command proves the claim, or mark the task complete. Each
call replaces that obligation's current references; immutable captured runs remain.
Use repeated `--run`, `--diagnostic-run`, and `--artifact` options for multiple
references. Concurrent `init` and `record` writers coordinate through the same directory
lock and receive a retryable lock error when another writer holds it. Manual editors do not participate in this advisory lock.

Validate work in progress:

```sh
python3 skills/confidence-protocol/scripts/confidence.py validate
```

Check that required evidence and report gates are complete:

```sh
python3 skills/confidence-protocol/scripts/confidence.py validate --require-complete
```

Render the readable report:

```sh
python3 skills/confidence-protocol/scripts/confidence.py render
```

### Handing evidence to another checkout

Validation checks the source locations recorded in supporting runs, not the caller’s current checkout. Success output and rendered reports list recorded working directories, source roots, binding kinds, run IDs and start/end observation status, grouped by recorded scope. Exact record versions and fingerprints remain in `runs/<id>.json`. Copying evidence does not certify another checkout; rerun verification there before claiming its current code. Multiple recorded roots are supported. Diagnostic runs and partial observations are labeled and do not certify current code; unknown or legacy binding remains explicit.

Captured runs store command output, exit status, time, log hash, and source fingerprints
before and after execution under `.confidence/runs/`. A current-code pass requires
known, matching source fingerprints and a fresh validation check. An observed source
change invalidates the supporting run. These observations do not prove that a
transient change-and-revert never occurred, or cover ignored dependencies and
external services. Binding covers Git-enumerated regular files and symlinks;
untracked special inputs such as named pipes are outside that scope. A run stops after 30 minutes or 10 MB of output by default.

Keep evidence in its usual untracked `.confidence` directory. Tracked evidence is
source input: editing a tracked report can invalidate earlier runs. Generated output
and reserved atomic temporary names are excluded only when untracked and regular;
do not place source inputs in those output namespaces. Concurrent publishers can
trigger one fresh inventory retry when an enumerated file disappears. Historical
version-1 captures remain readable as partial observations; rerun them to support
current-code completion. Missing Git still permits capture, but produces unknown
source binding. Partial reports remain renderable; they cannot pass completion.
Research completion is labeled separately and does not certify current code.

Content binding also works before the first Git commit. Nested repositories,
submodules, and explicit Git routing/index overrides remain unsupported for a
repository code claim; capture scoped checks from a supported component root or
retain partial evidence. Captures using the older Git-diff binding require reruns
under the content-binding algorithm.

Successful validation confirms the report's mechanical evidence checks. Agents and
reviewers remain responsible for whether the checks establish the task's claims.

Use `diagnostic_run_ids` for expected failures, such as the failing test before a bug
fix. Use `run_ids` only for successful evidence that supports a final claim.
After each captured run, use `record` to attach its ID and your assessment to the
matching obligation. Run plain `validate` while collecting evidence. Run
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
