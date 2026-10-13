# Model and harness guidance

Resolve the installed runtime and the exact requested model before dispatch.
Preserve cost/data authorization already granted. Do not silently substitute a
model or change access to make a benchmark run. Keep volatile vendor details in
dated research rather than the always-loaded skill.

Apply [model routing](model-routing.md) when dividing normal task work: bounded
discovery can use qualified lower-cost workers, while consequential decisions and
required reviews retain suitable owners. Use native delegation first when it fits;
use Claude Code for authorized provider diversity or additional available capacity.

## Separate four judgments

1. Model/tool proposal: what action and arguments were requested?
2. Harness acceptance: did permissions, schemas and runtime guards accept it?
3. Execution and persistence: did the action terminate and leave its intended state?
4. Obligation proof: does current, relevant evidence support the product claim?

A spawned agent, accepted job, zero exit, final message, completed turn, or valid
JSON is insufficient alone. Await actual terminal state and inspect logs/receipts,
including child tool errors. Aggregate parent permission-denial lists may omit
nested failures. Preserve actual model identifiers, runtime versions, role/scope,
session references, cost estimates and unsuccessful attempts in local audit data.
Do not expose credentials or private transcripts in research artifacts.

## Codex

Use the host's available agents for scoped work and the installed app-server schema
when building a runtime integration. Inherit model/effort unless an authorized
override is needed. Multi-agent tool names, concurrency, compaction, approvals and
state resources differ across desktop, CLI, Responses and managed Agents API;
documentation for one is not evidence about another. Retain proof state on disk
and recompute readiness after context compaction. Do not reconstruct approvals or
pending side effects from prose summaries.

## Claude Code support

Use noninteractive Claude Code for authorized offloaded research, proof design and
adversarial review. Pass argv through a structured subprocess call or file, avoid
shell interpolation, and preserve the exact requested model. A useful read-only
research envelope exposes only Agent, Read, Glob, Grep, WebSearch and WebFetch and
explicitly allows those tools; other tools remain denied. A tool list selects
availability, not permission. Match tools, permissions and budget to the task;
never use a blanket permission bypass as a routine repair.

Capture the actual process and retain its JSON receipt. Validate terminal result,
requested/actual model IDs, native subagent counts and nested failures. A model's
self-description is weaker than runtime usage metadata. Structured output proves
shape; inspect substantive findings. Use public source packets or specifically
authorized repository material, and ask reviewers a falsifiable counterexample
question with raw relevant evidence. Different model families can expose different
errors but are not statistically independent oracles. Do not request or use hidden
chain-of-thought as proof.

Hook semantics vary by event. A nonzero hook exit is not universally blocking, and
PostToolUse cannot undo an action. Keep the CLI evidence gate usable independently
of hooks; an optional adapter must test its real refusal semantics before claiming
enforcement. This release adds guidance, not an installed hook or launcher.

### Calling Claude from Codex

Codex can remain the task owner and invoke Claude Code as a bounded subprocess.
Use one fresh context for a specific role: proof design before implementation,
an adversarial check afterward, or a separately owned implementation slice.
Supply the requirements and relevant source instead of asking the peer to endorse
the owner's conclusion. A review needs read access and narrowly confined test
execution; an implementation slice needs explicit file ownership and write access.

Return a durable artifact containing the role, question, requested and observed
model metadata, provider/runtime version, session reference, source digest, actual
checks, findings, gaps and usage. Codex should reconcile concrete findings, repair
real defects, and capture fresh proof for the resulting source. A timeout,
unsupported model, missing receipt or incomplete required review remains a gap.
Never retry reviews merely to obtain agreement or treat a peer's prose as an
executed check. Do not request hidden reasoning.

For a staged workflow, give peers their own bounded windows outside the main
implementation subprocess's timer while retaining an aggregate task deadline.
For a model-triggered tool callback, account for time spent awaiting the peer
inside that call; it can exhaust the caller's window. Test the actual callback,
returned receipt and subsequent main response before claiming delegation works.
Validate the effective tool inventory: disabling shell tools alone may leave a
patch tool, resource handlers or delegation tools available. Keep credentials in
the provider process and expose only authorized source to its execution children.

Qualify the composed workflow using its actual child cwd, configuration paths,
sandbox, environment and executable resolution. Component probes alone can miss
delivery failures. Run the task's visible baseline checks through that same tool
boundary before interpreting model results. Supply an empty confined home when
tests need one, and keep writable test scratch outside a source tree that tests
copy; a temporary destination inside its own input can recurse. Preserve both
normal-completion and forced-timeout receipts. Reap an exited direct child before
escalating original-group cleanup on systems where unreaped zombies affect group
signals; still stop live group members and retain genuine cleanup failures.

When cross-provider cost and source exposure are authorized, use independently
available accounts when scoped work benefits from additional capacity or independent
coverage. Account availability does not grant authority. This does not combine or raise
their quotas. Preserve missing dollar costs
as unknown and distinguish reported list-price estimates from subscription
billing. Model availability can differ between desktop and CLI under the same
login; a catalog entry is not a successful request. Cross-provider review is a
candidate route to better coverage, with accuracy established by behavioral
checks and comparative trials rather than vendor identity or agreement.

### Packet-only Claude call from Codex

Use this pattern when the Claude worker needs only supplied text, for example for
research, proof design, or review of a packet. Codex stays the launchpad and owner.

- Place only authorized source in a fresh packet directory, and use it as the
  working directory.
- Keep client authentication in the provider process. Never copy tokens, keys, or
  credential files into the packet, the arguments, or the environment of any
  executable child.
- Invoke noninteractive mode through an argv list, without shell interpolation.
- Set the requested model and effort explicitly, using the options that the
  installed version's help output documents. If effort cannot be set, record that
  as a gap.
- Give the call an empty tool inventory. Confirm from the receipt that no tool calls
  occurred. An instruction not to use tools is not confinement.
- Bound each call with its own timeout under the aggregate task deadline. On
  timeout, stop the process group and reap the child. Retain the partial receipt as
  a gap.
- Request structured output. Check the exit status, the terminal result status, the
  error flag, the requested and actual model identifiers from runtime usage
  metadata, the absence of tool use, and usage.
- Treat a mismatch or a missing field as a gap. Do not substitute silently.

An edit route, such as an isolated low-risk edit or a difficult implementation
slice, needs a qualified actual tool boundary:

- an isolated worktree or snapshot;
- an effective tool inventory read from the runtime;
- a write scope enforced by sandbox or filesystem permissions, not by the prompt;
- confined test execution;
- no production credentials.

The owner then inspects the diff against the owned files and reruns the affected
proof.

## T3 Code and borrowed project patterns

T3 Code manages provider sessions through provider-specific adapters. Discover
capabilities such as rollback, model switching, compaction and continuation from
the actual provider/installed version. A UI checkpoint and a completed provider
turn do not prove an obligation. Keep runtime lifecycle separate from durable
proof, preserve source scope and reconcile interrupted state before retrying.

Borrow bounded patterns rather than replacing the native agent loop: routed
context from repository-map designs, durable task state from checkpointed graphs,
isolated delegation from agent SDKs, and independent grading from evaluation
harnesses. Read and pin actual upstream source, record license and limits, and
test the borrowed behavior. Reject skipped expected regressions, fabricated test
output and source leakage into a supposedly held-out oracle. Keep source/test
correctness separate from claims of reduced user intervention or improved model
accuracy; those need representative controlled task trials.

The dated [research report](https://github.com/e3-solutions/tweed/tree/main/docs/research/2026-10-confidence)
contains model specifications, pinned source comparisons, provenance and the
evaluation plan for this change. It is repository-only and is omitted from the
installed plugin archive.
