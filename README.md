# Tweed

Tweed is a small Codex workflow runner for evidence-backed root-cause analysis,
solution scoping, implementation, and review with parallel subagents. Linear is
the durable handoff between completed phases.

## How it works

Tweed keeps investigation, clarification, and agent activity inside the active
Codex thread. It writes to Linear only after a phase passes its completion gate:

```text
problem → RCA and clarification → create Linear issue
Linear RCA → solution scope and clarification → update the issue
Linear scope → implementation → update the issue
Linear implementation → independent review → update the issue
```

Each phase starts a fresh Codex thread. Downstream phases read the complete
handoff from Linear through the configured Linear MCP server, so another person
can continue the task without the earlier conversation.

## Prerequisites

- Python 3.10 or newer
- `uv`
- Codex or the ChatGPT desktop app
- The Linear MCP server connected to Codex with OAuth

Configure Linear MCP if needed:

```sh
codex mcp add linear --url https://mcp.linear.app/mcp
codex mcp login linear
```

## Install

For local development:

```sh
mkdir -p ~/.local/bin
ln -s "$(pwd)/tweed" ~/.local/bin/tweed
```

Ensure `~/.local/bin` is on `PATH`.

## Configure a folder

From a repository, set the Linear project that new Tweed issues should use:

```sh
tweed project set "Customer Experience"
```

Tweed stores this preference in `~/.config/tweed/config.json`, keyed by the
repository root. Running Tweed from a subdirectory uses the same setting.

Show or clear it with:

```sh
tweed project
tweed project clear
```

`TWEED_CONFIG` may point to a different config file.

## Root-cause workflow

```sh
cd /path/to/project
tweed root-cause "The merged export sometimes contains duplicate customers"
```

Tweed investigates with independent subagents. If a material fact cannot be
discovered from the repository, it asks one question in the terminal and
continues in the same Codex thread. No Linear issue is created unless the RCA
is fully established. After the completion gate passes, Tweed creates exactly
one issue in the configured project.

## Scope the solution

Pass the Linear issue identifier created by the RCA phase:

```sh
tweed scope ENG-123
```

Tweed reads the completed RCA from Linear. It may ask material product or
architecture questions locally, then updates the same issue once after the
scope is complete. The issue description preserves the RCA and adds the final
scope, non-goals, acceptance criteria, implementation plan, risks, and
validation.

## Scope a new feature

```sh
tweed feature "Let users export the filtered customer list as CSV"
```

Feature scoping uses the same clarification behavior and creates a Linear issue
only after the final scope passes its completion gate.

## Implement and review

Both phases use the Linear issue as their complete input:

```sh
tweed implement ENG-123
tweed review ENG-123
```

Implementation may edit the local repository but does not commit, push, open a
PR, or deploy. Review independently audits the integrated changes and may apply
bounded in-scope corrections. Each phase updates Linear once, only after its
completion gate passes.

## Non-interactive use

When standard input is not a terminal, Tweed cannot collect a clarification
answer. It returns the `Status: needs-input` question and exits with status 7.
Run the command interactively to answer and continue.
