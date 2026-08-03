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
- A Linear OAuth application client ID authorized once with `tweed auth login`

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

## Connect Linear

Create a private OAuth application from Linear's
[application settings](https://linear.app/settings/api/applications/new) using
the checked-in [`linear-oauth-app.json`](linear-oauth-app.json) values. The
redirect URI must be exactly `http://localhost:43817/oauth/callback`. Copy the
public client ID; no client secret is needed for Tweed's PKCE flow. Then run:

```sh
tweed auth login --client-id YOUR_CLIENT_ID
tweed auth status
```

If a browser cannot return to localhost, use `tweed auth login --manual` and
paste the complete redirected URL. `tweed auth logout` attempts to revoke both
rotating tokens, always removes them locally, and warns if Linear does not
confirm revocation; `--local-only` skips the remote attempt.

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

Tweed also disables configured Linear MCP servers inside every child model
session. All runner-initiated Linear I/O goes through the deterministic parent
transport. Known Linear credential and adapter environment variables are blanked
for child models.

Every child Codex session is pinned to `gpt-5.6-sol` with medium reasoning.
Spawned implementation and review agents inherit that same model and effort,
so all phases use one reproducible execution profile.
Linear credentials and adapter overrides are blanked in every model child
environment; the runner never forwards authentication to a model child.

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
update Linear data. The bundled standard-library adapter uses Linear's
authorization-code OAuth2 flow with PKCE S256 and talks directly to the fixed
GraphQL endpoint. Access and rotating refresh tokens stay in the operating
system credential manager and are never placed in argv, prompts, receipts, run
artifacts, or model-child environments. This is a non-forwarding boundary, not a
sandbox against arbitrary same-user code that can access an unlocked OS credential
store. Refresh is serialized, crash-recoverable within Linear's documented replay
grace, and atomic. An explicit
`TWEED_LINEAR_OAUTH_FILE` enables a `0700`/`0600` file backend for hermetic tests
or headless systems that supply their own filesystem isolation.

Personal API keys remain an explicit headless fallback only:

```sh
TWEED_LINEAR_AUTH=api-key LINEAR_API_KEY=... tweed scope ENG-123
```

`TWEED_LINEAR_ADAPTER` remains an unauthenticated protocol override for hermetic
tests and compatible installations; Tweed does not forward its credentials to
external adapters.

The issue description remains the stable original request and workflow index.
Every successful RCA, scope, implementation, and review is one append-only,
human-readable Linear comment containing the complete handoff plus a strict
hash-chain envelope. Tweed derives the legal stage from the unique validated
chain, uses deterministic issue/comment IDs to recover ambiguous writes, and
blocks on stale snapshots, malformed records, conflicting duplicates, or
forks. It never overwrites human prose. See [`docs/linear-adapter.md`](docs/linear-adapter.md).

Linear's public comment mutation has no documented predecessor precondition, so
Tweed does not claim server-side atomic CAS. A cross-host concurrent append can
briefly create a fork; mandatory post-write and next-phase validation detects
it and fails closed. Linear comments are user-editable/deletable: Tweed detects
edits, archives, forks, missing interior records, and deletion relative to a
persisted frozen head, but a fresh client cannot prove that a now-deleted tail
once existed. Retry synchronization never reruns completed reasoning.

Linear's hosted MCP endpoint is intentionally not used for transport: its
current create tools lack caller-supplied IDs/idempotency keys, and its comment
reader lacks archived-inclusive edit/archive metadata required by this journal.

## Deterministic evidence reuse

Phase coordinators may run `tweed evidence` with exact command arguments and
declared dependency/lockfile, configuration, environment, tool-version,
execution-timeout, and run-artifact inputs. Every empty input class requires an explicit `--no-*`
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
