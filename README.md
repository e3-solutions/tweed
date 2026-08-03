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
- An officially authenticated, atomic Linear adapter configured with
  `TWEED_LINEAR_ADAPTER`

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
Its child sessions disable lifecycle hooks and the local `linear-progress-sync`
orchestrator because those hooks own the same branch, Linear, and PR boundaries;
only the Tweed runner may own those writes. Global hooks remain enabled outside
Tweed-created sessions.

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

Full reports, frozen Linear snapshots, workflows, and evidence are stored as
private content-addressed artifacts under `~/.local/state/tweed/runs/`.

## Linear transport

Tweed never starts a model session to read, copy, compare, format, create, or
update Linear data. `TWEED_LINEAR_ADAPTER` names an executable implementing the
`dev.tweed.linear.v1` JSON protocol on standard input/output. Authentication is
owned by that explicitly configured adapter; Tweed does not inspect Codex MCP
storage, export OAuth credentials, or accept a read-then-write emulation.

The adapter must provide an atomic compare-and-swap over the exact UTF-8 issue
description, conditioned on both its opaque authoritative revision and its
SHA-256 digest. If no officially authenticated adapter with that guarantee is
configured, Tweed fails closed before starting phase reasoning. See
[`docs/linear-adapter.md`](docs/linear-adapter.md) for the narrow protocol.
Any stale or formatting-altered authoritative description remains
`sync-blocked`; retrying synchronization never reruns completed reasoning.

## Deterministic evidence reuse

Phase coordinators may run `tweed evidence` with exact command arguments and
declared dependency/lockfile, configuration, environment, tool-version, and
run-artifact inputs. Every empty input class requires an explicit `--no-*`
assertion. Tweed reuses only a complete identical key and recomputes on any
change or uncertainty; reviewer reasoning is never cached.

## Codex adapter mode

The future `use-tweed` Codex skill invokes the same commands with `--agent`:

```sh
tweed --agent create problem "..."
tweed --agent root-cause ENG-123
```

Agent mode emits exactly one bounded JSON receipt and never prints the complete
phase report, keeping the calling Codex context small.
