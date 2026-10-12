# Route work by risk, checkability, and cost

Use this guidance when a substantial task has useful work that can be delegated.
It governs normal use of Confidence Protocol through the host's native agents or
an authorized external harness. It does not install a dispatcher or make `next`
launch models. Preserve the task's existing authority, proof mode, and required
reviews. A fixed experiment's registered routes govern route selection; they do
not override authority, proof mode, or required reviews.

## Choose a route before dispatch

Prefer a qualified lower-cost worker for a narrow question with inspectable
answers: finding source locations, mapping a bounded component, extracting facts
from supplied evidence, proposing missing test cases, or identifying candidate
counterexamples. Native Luna or Claude Haiku can be candidates when available;
names alone establish neither price nor suitability. A cheap worker may propose
an obligation, test, or defect; the owner must check the relevant source or execute
the proposed check before promoting it into the contract or proof.

Use a capable implementation worker for an isolated edit with explicit file
ownership and observable acceptance criteria. Terra, Sol, Sonnet, or another
available model may fit this role. Terra is not automatically the cheaper route.
Treat changes to trust, persistence, external contracts, or several interacting
components as consequential even when the individual edits look small.

Use the strongest suitable owner or advisor for consequential ambiguity,
cross-component decisions, conflicting findings, and final proof assessment.
Required Critical proof design and adversarial review need suitably capable,
independent reviewers with separate origins and contexts. A smaller model can
assist those reviewers with bounded evidence work; assistance does not replace
the required roles. Different model names do not establish independence.

Choose by the failure consequences, uncertainty, coupling, and ease of checking
the output, rather than a fixed model ladder. Reuse inspectable qualification from
earlier tasks when its model, harness version, tool boundary, task class, and limits
still apply. Retain its date, evidence reference, and observed failures; a model
name in a handoff is insufficient. For a new route, qualify it on a representative
bounded task and check its actual tools, permissions, output, and failure behavior.
Recheck affected boundaries after a relevant runtime change or observed failure.
Do not turn one successful example into a general accuracy claim.

The first bounded shard of real work can provide that qualification when the owner
checks its findings and actual tool behavior; an extra demonstration call is not
required. Retained task artifacts are durable even when untracked. Reuse accessible,
dated receipts instead of requalifying every dispatch.

## Make cheap depth useful

Give each worker one question, an authorized source scope, a bounded context,
expected artifact, and a stopping condition. Prefer independent shards that cover
different uncertainty over several agents reading the same full transcript.
Provide requirements and raw relevant evidence instead of the owner's proposed
answer. Distinguish observed facts, candidate explanations, proposed checks, and
missing information. Require source locations or evidence identifiers for claims;
keep unsupported statements explicit rather than filling gaps from memory.

For edits, name owned files, state that other agents are working in the repository,
and require accommodating their changes within the worker's owned scope. Route
needed edits outside that scope through the owner, who serializes the change or
explicitly reassigns ownership. Serialize shared writes and dependent
decisions. Separate worktrees can isolate parallel edits; integrate them before
final proof. Concurrent changes in one checkout can stale captures even in other
files, because source binding covers the inventory. Capture on a stable integrated
tree and rerun affected proof after integration. Keep exploration and test proposals
read-only unless implementation or artifact creation is authorized. Use deterministic
search, parsing, or tests directly when they answer the question with less effort
than model delegation.

The owner checks every finding used to choose a consequential action or claim
completion. Read the cited source at the relevant revision, reproduce alleged
failures when applicable, and capture actual checks through the normal evidence
workflow. A worker's summary, confidence score, agreement, or valid JSON is not
executed proof. Preserve useful findings and unresolved gaps when a worker fails.

Check completeness and negative claims separately: require the search scope and
method behind statements such as "all callers" or "no other writer". Rerun the
relevant deterministic search or reference analysis before relying on that scope.
Reading only the worker's positive citations cannot detect omitted components;
unverified completeness stays a gap.

When enumeration is cheap, run it directly and give workers the resulting set to
classify or explain. That avoids using a model to repeat a deterministic listing.
For consequential trust, persistence, or destructive-data work, check each route's
effective tool and permission envelope. A read-only instruction is not confinement;
if the native host cannot provide the needed boundary, supply a source packet or
isolated snapshot without production credentials and restrict execution appropriately.

## Escalate and recover

Escalate a bounded question when its answer lacks usable evidence, contradicts
current source, remains disputed after a focused check, or reveals consequential
ambiguity or coupling. After a failed attempt, first inspect the failure and
change the relevant scope, evidence, tool access, or model. Repeated attempts
without new evidence should lead to a different approach or a precise blocker.
Do not keep a cheap route merely to avoid reporting a gap.

Switch to direct ownership or a better qualified route when worker verification
and repair consume more effort than doing that kind of work directly. Record the
reason and reuse the failed attempt's useful evidence; do not repeat it solely
because its model has a low advertised token price.

If an owner-chosen model or tool boundary is unavailable, preserve the unsuccessful
attempt and use an available qualified route, or do the work directly. Record the
substitution and its reason. When the user names a model, disclose a substitution
in the final report; if that model is a requirement, preserve the blocker and finish
independent work. Within a registered evaluation, apply only its explicit fallback
rule; if it has none, do not substitute, even with disclosure. An incomplete required
review remains incomplete until a qualified reviewer performs it. Ordinary routing choices
within authorized scope do not require another user confirmation. Use native host
delegation within that authority; separately billed or cross-provider calls must
remain within granted cost and source-exposure authorization.

## Account for the whole route

Compare cost per verified useful outcome, including startup, context transfer,
cache behavior, worker output, owner verification, and repair. A lower token price
can still produce a more expensive result. Check current prices and the actual
account's model availability once when selecting a route for the task; reuse that
dated information unless a relevant change or failure calls for a recheck. API list prices do not
establish subscription billing, and smaller does not always mean cheaper.

Record requested and observed model identifiers separately, role, effort setting,
source scope, actual outcome, and available usage in authorized local task evidence.
For read-only work without authorized artifact creation, report that metadata and
its gaps in the response instead of writing an evidence directory.
Finalize arbitrary delegation artifacts before source-bound capture, or use an
already authorized, intentionally ignored task evidence location. Unignored files
are source inputs; do not broaden exclusions to hide code or force current proof.
Reference retained artifacts and digests from the task evidence rather than adding
unsupported routing fields to the report schema. Worker captures are usable when
their role permits evidence writing and the owner inspects logs and source binding;
read-only workers without that authorization do not capture.
Preserve unobserved usage and dollar costs as unknown. A desktop catalog entry,
successful CLI request, and runtime model receipt provide different evidence.
Use [harness guidance](harnesses.md) for actual terminal state, confinement,
cross-provider calls, time budgets, and truthful cost reporting.

Keep routing proportional: a direct Quick edit may need no model worker. For a
complex task, spend available parallel capacity on ready work that resolves
distinct uncertainty, then reconcile it before changing dependent claims. More
agents, cheaper tokens, or broader provider usage do not establish better accuracy;
compare completed behavior and proof against a suitable baseline before claiming
an improvement.
