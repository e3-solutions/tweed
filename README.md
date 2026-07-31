# Tweed

Codex-native adversarial workflows for turning software problems into verified
understanding and implementation contracts.

## Workflows

Tweed has five separate workflows. `root-cause` identifies the
problem and establishes its cause. `scope` takes that completed RCA and
identifies the smallest complete solution scope. `feature` turns a new feature
request into a constrained scope and ordered implementation plan. These three
are read-only. `implement` and `review` are the two write-capable phases:
implementation executes an approved scope, while review independently audits
the result and applies bounded corrections until no validated material findings
remain.

Independent Codex subagents challenge the evidence and proposal from distinct
axes. The final reports include compact maps of the agents used and how each
conclusion affected the result. The workflow prompts belong to Tweed; they are
not installed as Codex skills.

Feature and solution scoping include a dedicated reuse-research agent that
checks project utilities, language/framework built-ins, installed libraries,
exact versions, and primary documentation before proposing custom code.

## Install

Tweed uses the official Python Codex SDK to start the installed Codex App
Server in the background. It creates a persistent Codex thread for the current
project and sends the investigation directly to that thread; it does not open
or automate the Codex terminal UI. `uv` manages the single SDK dependency.

```sh
mkdir -p ~/.local/bin
ln -s /Users/aryagm/code/tweed/tweed ~/.local/bin/tweed
```

Ensure `~/.local/bin` is on `PATH`. Then, from any project, run:

```sh
cd /path/to/project
tweed root-cause
```

Tweed asks for the problem, then sends it to a new Codex thread in the
background. You can also provide it directly:

```sh
tweed root-cause "The merged export sometimes contains duplicate customers"
```

Save an established RCA, review it, and pass it into the separate scoping step:

```sh
tweed root-cause "The merged export sometimes contains duplicate customers" > /tmp/rca.md
tweed scope /tmp/rca.md > /tmp/scope.md
```

`scope` also accepts the RCA on standard input. It refuses to start unless the
report begins with `Status: established`. Each step gets a fresh Codex thread,
and none changes project files, writes to Linear, or implements anything.

For a new feature:

```sh
tweed feature "Let users export the filtered customer list as CSV" > /tmp/scope.md
```

The feature report captures the user outcome, proposed solution, change
surface, ordered implementation steps, non-goals, acceptance criteria, risks,
validation, alternatives, assumptions, and the conclusions of every agent
used. It scopes the work but does not execute it.

After reviewing either kind of scoped report, implement it separately:

```sh
tweed implement /tmp/scope.md > /tmp/implementation.md
```

`implement` refuses anything that does not begin with `Status: scoped`. It
preflights repository state, assigns disjoint write surfaces to bounded
subagents, independently reviews the integrated diff, and runs the relevant
checks. A Git repository is required so Tweed can detect partial or unexpected
workspace changes. It may edit project files, but it does not commit, push,
open a PR, write to Linear, deploy, or broaden the approved scope.

Run the independent review-and-fix loop against the same approved scope:

```sh
tweed review /tmp/scope.md /tmp/implementation.md
```

`review` uses independent simplicity/reuse, robustness, compatibility,
performance, and verification agents. They actively seek code to delete,
simplify, replace with verified existing capabilities, or make measurably more
efficient. Reviewers do not edit; bounded fixers address validated findings,
affected surfaces are re-reviewed, and a final whole-diff clean pass must
report zero material findings. Like implementation, review may edit local files
but performs no delivery or external writes. Reports are shown under `/tmp` so
shell redirection does not itself alter the project under review.
