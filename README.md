# Bonaparte

Bonaparte takes one software request from a human-readable Linear issue to a
reviewed, ready-to-merge GitHub pull request. Each phase starts a fresh local
Codex task; Linear is the durable handoff, and the invoking task sees only a
bounded JSON receipt.

Before each non-create phase, the runner deterministically fetches Linear and
passes only the latest phase-specific handoff: intake to RCA, RCA or feature
intake to scope, scope to implementation, implementation to review, and review
to publish. The issue's official `gitBranchName` is preserved as metadata for
implementation.

```text
Bug:     create → RCA → scope → implement → review → publish
Feature: create → scope → implement → review → publish
```

## Install

Bonaparte uses your local Codex installation and its authenticated Linear MCP. The
implement, review, and publish phases also use your existing Git and GitHub CLI
authentication.
Every phase coordinator is pinned to `gpt-5.6-sol` with medium reasoning, and
every spawned subagent is pinned to `gpt-5.6-sol` with medium reasoning.

Prerequisites:

- macOS or Linux with Git and Python 3.10+
- a working local `codex` command
- the GitHub CLI (`gh`) for draft and published pull requests

Copy and run this installer:

```sh
#!/bin/sh
set -eu
checkout=$(mktemp -d)
trap 'rm -rf "$checkout"' 0
git clone -q https://github.com/e3-solutions/tweed.git "$checkout"
"$checkout/install"
```

The temporary checkout is removed after installation. The installer copies
committed `HEAD` into a versioned snapshot under
`~/.local/share/bonaparte/releases/`. Two stable links select that snapshot:

- `~/.local/bin/bonaparte` → the active release's launcher
- `~/.codex/skills/use-bonaparte` → the active release's Codex skill

The checkout can then move between branches or be deleted without changing the
installed behavior. If `~/.local/bin` is not already on `PATH`, add it to your
shell configuration:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Connect the local Codex installation to Linear and authenticate GitHub:

```sh
codex --version
codex mcp add linear --url https://mcp.linear.app/mcp
codex mcp login linear
gh auth login
```

If those integrations are already configured, the add/login commands can be
skipped. Verify the installation without creating external work:

```sh
bonaparte --help
codex mcp list
gh auth status
```

For a non-default location, set `BONAPARTE_BIN_DIR`, `BONAPARTE_HOME`, or `CODEX_HOME`
when running `./install`.

## Updates

At most once per day, Bonaparte checks the public repository for the highest stable
`vX.Y.Z` tag. It fetches that exact Git ref into a new directory and smoke-tests
it before switching the active release atomically. A failed check never prevents
the installed runtime from starting.

```sh
bonaparte update
```

Set `BONAPARTE_AUTO_UPDATE=0` to disable the daily check. Run `./bonaparte` directly
when developing against a live checkout.

Maintainers publish an update by pushing a stable tag such as `v0.2.0`. Configure
the public repository to protect `v*` tags from modification. No release archive
or package registry is required.

## Commands

```sh
bonaparte create bug "problem given by user"
bonaparte create feature "capability requested by user"
bonaparte RCA LIN-123
bonaparte scope LIN-123
bonaparte implement LIN-123
bonaparte review LIN-123
bonaparte publish LIN-123
bonaparte resume RCA <session-id> "clarification answer"
```

- **Create** writes a human title and a `What`/`Why`/`How` description for a bug
  or feature. It adds no comment.
- **RCA** delegates independent reproduction, tracing, and falsification work,
  then writes the first Bonaparte comment.
- **Scope** turns an established bug cause or feature outcome into the smallest
  implementation-ready plan after independent reuse, simplicity, and
  robustness analysis.
- **Implement** creates or reuses the official Linear branch and one draft PR,
  then pushes each coherent, verified implementation commit to that draft.
- **Review** independently challenges the complete diff, applies only verified
  in-scope corrections, pushes any correction commits to the same draft, and
  records the final commit.
- **Publish** verifies and finalizes that draft, marks it ready for review, and
  records its URL in Linear. It never merges or deploys.

When a user asks an agent to use Bonaparte, the skill selects the bug or feature
route, runs the commands in sequence, and passes only the Linear issue identifier
between them. Any `needs-input`, `blocked`, or failed phase stops the chain.
After `needs-input`, `resume` continues the same coordinator session with the
answer instead of restarting its investigation.

## Review liveness for trusted hosts

Review has an optional, host-controlled liveness channel. Before launching
Bonaparte, a trusted host may open a writable file descriptor numbered 3 or
higher, configure it as nonblocking, explicitly inherit it into the launcher,
and set
`BONAPARTE_PROGRESS_FD` to that descriptor number. The launcher preserves the
descriptor when it replaces itself with the runner. Update subprocesses do not
inherit it. This ABI is review-only: other phases emit no progress events.

The channel is UTF-8 JSON Lines. Every line has exactly these fields:
`version`, `sequence`, `phase`, `state`, and `elapsed_seconds`. `version` is `1`,
`sequence` is a monotonically increasing integer, `phase` is `"review"`, and
`elapsed_seconds` is a nonnegative number measured from the start of review and
rounded to milliseconds.
`state` is one of `started`, `active`, `finalizing`, `completed`, `needs-input`,
`blocked`, `failed`, or `interrupted`.

Emission is best effort: `started` is immediate, `active` is a periodic
heartbeat every 10 seconds while the coordinator runs, and `finalizing` follows
heartbeat shutdown and join. At most one terminal event follows, and it matches
the validated final receipt. The channel contains no prompts, model events,
issue or customer data, repository contents or paths, command output, secrets,
URLs, or contact details.

The host-supplied descriptor must already be nonblocking; Bonaparte rejects a
blocking descriptor without changing its blocking mode. An invalid descriptor
or any encoding, size, partial write, or write error permanently disables
progress for that process. Bonaparte does not retry and never falls back to
stdout, stderr, a file, or a service.
Regardless of progress availability, stdout remains exactly one final JSON
receipt of at most 4 KiB; stderr remains the diagnostic channel. Progress only
proves process liveness. It does not mean that native review ran successfully,
that findings were resolved, or that the review receipt will be `completed`.
