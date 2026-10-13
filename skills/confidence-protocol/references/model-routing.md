# Route work by risk, checkability, and cost

Use this guidance when a substantial task has work worth delegating. It adds no
dispatcher, and `next` does not launch models. Routing never changes the task's
authority, proof mode, or required reviews. A registered experiment's fixed routes
govern route selection inside that experiment only.

## Default roles

| Responsibility | Route | Check before relying on it |
| --- | --- | --- |
| Difficult bugs, substantial or coupled implementation and its repair, design alternatives | Claude Opus (`claude-opus-5-5`) as development lead | Executed acceptance checks on the integrated tree, not the lead's summary. |
| Bounded discovery: source maps, evidence extraction, candidate questions or test cases | Claude Haiku (`claude-haiku-5-5`), only when checking its output costs less than producing it | Retrace cited source; rerun any completeness search. |
| Mechanical edits fully decided by a deterministic check | Haiku or direct | Inspect the diff and run that check. |
| User conversation, authority, integration, focused independent checks, fallback | Codex when it coordinates; otherwise the session owner | Current evidence and the contract pairing in `SKILL.md`. |
| Required Critical proof design and adversarial review | Separate capable actors with separate contexts; keep a non-implementer role when Opus implements | Each role's scope, evidence and unresolved findings. |

Opus leads development: give it the contract, owned files and acceptance checks,
and let it run its own implement/check/repair loop to completion or a precise
blocker. It returns the diff, the commands it executed with their outcomes, and
remaining gaps. Codex is the interface, independent checker and backup. It does not
redo delegated work; it reruns focused acceptance checks and asks one
counterexample question where risk warrants. Each finding that affects a stated
requirement goes back to Opus as a packet: the requirement, the concrete
counterexample or source location, and the executed or reproducible check. Opus
repairs, reruns the affected checks, and returns the current diff and remaining
gaps; Codex rechecks the affected behavior and integrates. Other suggestions stay
optional. This handoff applies to delegated substantial work, not Quick tasks.

Codex takes over directly when a route is unavailable or stalls, or when a repair
is fully determined by the finding and cheaper than a handoff. It then becomes the
author of that repair: record the finding, changed paths and rerun checks, and do
not report its own passing check as independent post-repair review. Where
independent review is required, a separate actor that did not implement or repair
that scope performs it ([complex tasks](complex-tasks.md)).

Haiku is optional. Use it for a narrow question with inspectable answers, not as a
compulsory first step. In one small registered comparison, Haiku implementation
attempts recorded one verified success in twelve and six registered-oracle false
completions in six declarations; do not route substantial implementation to it
without new qualifying evidence. Different model names do not
establish independence, and a user's route preference is intent, not evidence of
accuracy or price. The owner, not a cheap classifier, decides that an edit is
low-risk; trust, persistence, external contracts and interacting components need
a capable route and their actual boundary proof.

Keep Quick work direct. Inside Claude Code, native subagents start without the
conversation history, so their brief must be self-contained; a subagent's `model`
field selects Haiku or Opus. If a preferred route is unavailable, do the work with
an available qualified route or directly, and record the substitution.

## Brief a worker

```
Role: <discovery | test proposal | implementation lead | proof design | adversarial review>
Question or outcome: <one falsifiable question, or the contract and acceptance checks>
Source scope: <files@revision or packet>; use nothing outside it
Tool boundary: <what the harness actually enforces>
Owned files (edits only): <list>; other agents may be editing; route other edits to the owner
Return: findings with source locations labeled observed fact, candidate
  explanation, proposed check or missing information; executed commands and
  outcomes; expected values with derivation; gaps
Stop when: <condition or budget>; then report partial results
```

Supply requirements and raw evidence, not the owner's proposed answer. Prefer
shards that cover different uncertainty over several agents reading the same
transcript. When enumeration is cheap, run it directly and give the worker the
set to classify.

## Verify what the worker returns

The owner checks every finding used to choose a consequential action or claim
completion: read cited source at the relevant revision, reproduce alleged failures,
and capture checks through the normal evidence workflow. A summary, confidence
score, agreement, majority vote or valid JSON is not executed proof. Completeness
and negative claims ("all callers", "no other writer") need a stated search scope
and method that the owner reruns; positive citations cannot show nothing was
missed.

```
Route:        requested model/effort | observed model | harness version | boundary checked
Terminal:     exit status | result status | nested tool errors | timeout
Findings:     promoted item -> source read | check run | outcome
Repairs:      finding -> repair actor | changed paths | affected checks rerun | post-repair reviewer
Completeness: scope and method rerun | remaining gaps
Critical:     proof-design origin | adversarial-review origin | separate contexts
Rejected:     unverified or contradicted findings, with reasons
```

## Boundaries, concurrency and recovery

A read-only instruction is not confinement. Claude Code permission rules do not
cover files opened by arbitrary subprocesses; OS-level sandboxing does. For trust,
persistence or destructive-data work, check each route's effective tool and
permission envelope, or supply a source packet or isolated snapshot without
production credentials. Serialize shared writes and dependent decisions; separate
worktrees isolate parallel edits but must be integrated before final proof.
Concurrent changes can stale captures in other files, so capture on a stable
integrated tree.

Reuse inspectable route qualification when its model, harness version, tool
boundary and task class still apply; the first bounded shard of real work can
qualify a new route when the owner checks its findings and tool behavior.
Escalate when an answer lacks evidence, contradicts current source, stays disputed
after a focused check, or reveals consequential coupling. Repeated attempts
without new evidence call for a different scope, route or a precise blocker.
Switch to direct ownership when checking and repairing worker output costs more
than doing the work.

When the user names a model, disclose any substitution; if that model is required,
keep the blocker and finish independent work. Within a registered evaluation,
apply only its explicit fallback rule. An incomplete required review stays
incomplete until a qualified reviewer performs it. Ordinary routing within
authorized scope needs no extra confirmation; separately billed or cross-provider
calls need authorization covering cost and source exposure.

## Account for the whole route

Compare cost per verified useful outcome, including context transfer, owner
verification and repair; a lower token price can produce a more expensive result.
Check current availability once per task and reuse that dated information.
Record requested and observed model identifiers, role, effort, source scope,
outcome and available usage in authorized task evidence, or in the response for
read-only work. Keep unobserved costs unknown. Finalize delegation artifacts before
source-bound capture or keep them in an intentionally ignored evidence location;
do not broaden exclusions to force current proof. See [harness guidance](harnesses.md)
for terminal state, confinement and cross-provider calls. More agents, cheaper
tokens or more providers do not establish better accuracy.
