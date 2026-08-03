# Tweed

Tweed is a strict Linear-backed Codex workflow for taking one software request
through root-cause analysis or feature scoping, implementation, independent
review, and a verified commit that is ready to merge.

## Lifecycle

Every request begins as a real Linear issue. Each command starts a fresh Codex
coordinator, reads the issue as its complete phase input, and advances exactly
one legal stage after its completion gate passes.

```text
Problem: create → root-cause → scope → implement → review → ready-to-merge
Feature: create → scope → implement → review → ready-to-merge
```

Linear is the baton between phases. Coordinators do not inherit earlier phase
conversations. Blocked, partial, and clarification results never advance the
issue.

## Prerequisites

- Python 3.10 or newer
- `uv`
- Codex or the ChatGPT desktop app
- Linear MCP connected to Codex with OAuth

For local development, make the script available on `PATH`:

```sh
mkdir -p ~/.local/bin
ln -s "$(pwd)/tweed" ~/.local/bin/tweed
```

## Configure a repository

Set the Linear project used for intake issues:

```sh
tweed project set "Customer Experience"
tweed project
tweed project clear
```

The setting is stored per canonical Git root in
`~/.config/tweed/config.json`. `TWEED_CONFIG` may select another file.

## Create an intake issue

```sh
tweed create problem "The merged export sometimes contains duplicate customers"
tweed create feature "Let users export the filtered customer list as CSV"
```

A problem starts at `needs-rca`; a feature starts at `needs-scope`.

## Advance one explicit phase

```sh
tweed root-cause ENG-123
tweed scope ENG-123
tweed implement ENG-123
tweed review ENG-123
```

Commands reject issues in the wrong stage. Root-cause analysis and scope are
read-only. Implementation creates a runner-owned `tweed/<issue>` branch in an
isolated worktree and commits a passing result. Review uses the same worktree,
applies only bounded in-scope repairs, commits any passing corrections, and
advances the issue to `ready-to-merge`.

Tweed does not push, open a pull request, merge, deploy, or delete its worktree.
Its child sessions disable the local `linear-progress-sync` orchestrator because
that plugin owns the same branch, Linear, and PR boundaries; only one runner may
own those writes.

Every child Codex session is pinned to `gpt-5.6-sol` with medium reasoning.
Spawned implementation and review agents inherit that same model and effort,
so all phases use one reproducible execution profile.

## Clarification

Interactive commands ask a material question in the terminal and continue in
the same Codex task. Non-interactive commands return a run ID and structured
question with exit status 7. Resume that exact task with:

```sh
tweed resume tw_0123456789abcdef "Use the existing export permission model"
# If a runner was interrupted, resume it without an answer:
tweed resume tw_0123456789abcdef
```

Full reports and workflow snapshots are stored privately under
`~/.local/state/tweed/runs/`.

## Codex adapter mode

The future `use-tweed` Codex skill invokes the same commands with `--agent`:

```sh
tweed --agent create problem "..."
tweed --agent root-cause ENG-123
```

Agent mode emits exactly one bounded JSON receipt and never prints the complete
phase report, keeping the calling Codex context small.
