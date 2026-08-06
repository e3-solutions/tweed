# Tweed

Tweed takes one software request from a human-readable Linear issue to a
reviewed, ready-to-merge GitHub pull request. Each phase starts a fresh local
Codex task; Linear is the durable handoff, and the invoking task sees only a
bounded JSON receipt.

Before each non-create phase, Tweed starts a separate read-only handoff loader.
It selects exact durable artifacts from Linear and passes only the phase's typed
context packet to the worker:

```text
RCA:       intake
Scope:     bug RCA | feature intake
Implement: scope
Review:    scope + implementation
Publish:   implementation + review
```

The worker receives issue identity metadata and those artifacts, not the full
issue description, comment history, activity, or earlier agent conversation.

```text
Bug:     create → RCA → scope → implement → review → publish
Feature: create → scope → implement → review → publish
```

## Install

Tweed uses your local Codex installation and its authenticated Linear MCP. The
publish phase also uses your existing Git and GitHub CLI authentication.
Every phase coordinator is pinned to `gpt-5.6-sol` with high reasoning, and
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

The installer creates two symlinks:

- `~/.local/bin/tweed` → this checkout's CLI
- `~/.codex/skills/use-tweed` → this checkout's Codex skill

Keep the checkout in place. If `~/.local/bin` is not already on `PATH`, add it
to your shell configuration:

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

For a non-default location, set `TWEED_BIN_DIR` or `CODEX_HOME` when running
`./install`. Because installation uses symlinks, pulling updates into this
checkout updates the installed CLI and skill immediately.

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
between them. Tweed resolves that identifier into the minimal internal handoff
automatically. Any `needs-input`, `blocked`, or failed phase stops the chain.
