# Tweed

Tweed takes one software request from a human-readable Linear issue to a
reviewed, ready-to-merge GitHub pull request. Each phase starts a fresh local
Codex task; Linear is the durable handoff, and the invoking task sees only a
bounded JSON receipt.

```text
Bug:     create → RCA → scope → implement → review → publish
Feature: create → scope → implement → review → publish
```

## Install

Tweed uses your local Codex installation and its authenticated Linear MCP. The
publish phase also uses your existing Git and GitHub CLI authentication.
Every phase coordinator is pinned to `gpt-5.6-sol` with medium reasoning, and
every spawned subagent is pinned to `gpt-5.6-sol` with medium reasoning.

Prerequisites:

- macOS or Linux with Git and Python 3.10+
- a working local `codex` command
- the GitHub CLI (`gh`) for publishing pull requests

Clone Tweed and run its installer:

```sh
git clone https://github.com/e3-solutions/tweed.git
cd tweed
./install
```

The installer copies committed `HEAD` into a versioned snapshot under
`~/.local/share/tweed/releases/`. Two stable links select that snapshot:

- `~/.local/bin/tweed` → the active release's launcher
- `~/.codex/skills/use-tweed` → the active release's Codex skill

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
tweed --help
codex mcp list
gh auth status
```

For a non-default location, set `TWEED_BIN_DIR`, `TWEED_HOME`, or `CODEX_HOME`
when running `./install`.

## Updates

At most once per day, Tweed checks the public repository for the highest stable
`vX.Y.Z` tag. It fetches that exact Git ref into a new directory and smoke-tests
it before switching the active release atomically. A failed check never prevents
the installed runtime from starting.

```sh
tweed update
```

Set `TWEED_AUTO_UPDATE=0` to disable the daily check. Run `./tweed` directly
when developing against a live checkout.

Maintainers publish an update by pushing a stable tag such as `v0.2.0`. Configure
the public repository to protect `v*` tags from modification. No release archive
or package registry is required.

## Commands

```sh
tweed create bug "problem given by user"
tweed create feature "capability requested by user"
tweed RCA LIN-123
tweed scope LIN-123
tweed implement LIN-123
tweed review LIN-123
tweed publish LIN-123
```

If a phase needs one clarification, answer it by resuming the same coordinator
session from the receipt instead of restarting the phase:

```sh
tweed --repo /path/to/repository resume RCA <resume_session_id> "The answer"
```

- **Create** writes a human title and a `What`/`Why`/`How` description for a bug
  or feature. It adds no comment.
- **RCA** delegates independent reproduction, tracing, and falsification work,
  then writes the first Tweed comment.
- **Scope** turns an established bug cause or feature outcome into the smallest
  implementation-ready plan after independent reuse, simplicity, and
  robustness analysis.
- **Implement** creates or reuses an issue branch, delegates bounded code
  ownership, validates the change, commits it locally, and records the handoff.
- **Review** independently challenges the complete diff, applies only verified
  in-scope corrections, reruns validation, and records the final commit.
- **Publish** pushes that reviewed commit, creates or recovers one non-draft PR,
  and records its URL in Linear. It never merges or deploys.

When a user asks an agent to use Tweed, the skill selects the bug or feature
route, runs the commands in sequence, and passes only the Linear issue identifier
between them. Any `needs-input`, `blocked`, or failed phase stops the chain.
