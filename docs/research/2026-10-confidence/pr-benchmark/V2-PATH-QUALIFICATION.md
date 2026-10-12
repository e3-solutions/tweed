# Qualification of a separate mixed-provider adapter

The first mixed-provider registration remains immutable. Its attempted and
unstarted assignments remain in that cohort's 48-assignment denominator. V2 is
a separate prospective experiment; it cannot repair the historical cohort or
establish a gain over either provider by itself.

## Confirmed transport failure

The first hybrid controller accepted a relative study directory. It passed a
relative `control` path to the unchanged Claude adapter, which wrote that path
into `server-config.json` and into MCP's `serve --config` argument. The sandbox
policy resolved its readable config path against the repository coordinator
cwd. Claude started the server from the temporary actor workspace, where the
relative config argument addressed a different path. Astra's adapter resolved
its controller path internally, so this failure was asymmetric.

This mechanism was reproduced without hosted inference by capturing the exact
MCP command constructed by the unchanged Claude adapter and executing it under
its actual sandbox policy and actor cwd. A relative config argument produced
exit 1, no MCP tools, and a config-path failure. An absolute argument produced
exit 0 and all seven expected tools. This is stronger than merely inspecting a
config or testing an MCP server directly from the coordinator cwd.

The original observed Claude initialization also contained only
`StructuredOutput` and reported `cp_trial` as failed. Those receipts cannot be
used as evidence that Claude successfully participated in a controlled
mixed-provider implementation. Successful model attribution or a terminal
answer does not establish transport availability.

## V2 change and checks

`hybrid_v2.py` imports the unchanged registered controller and resolves
`protocol`, `manifest`, `study`, and optional model-catalog paths before either
preparation or execution. It normalizes stage paths too. Before every model
stage, it starts the exact sandboxed MCP subprocess from the actor cwd,
initializes it, discovers all seven expected tools, and exercises `list_files`.
Readonly stages also attempt a forbidden source write and require denial.
Failed local qualification prevents inference. The new cohort uses separate
registration and receipt paths; the wrapper refuses a registration lacking its
V2 marker and exact source hash.

After an Opus stage, the wrapper requires live initialization to show
`cp_trial` connected and all seven expected MCP names. `StructuredOutput` is an
explicitly allowed schema-output tool; other extra tools invalidate the stage.
Missing initialization remains unknown, and unknown qualification is ineligible
for verified efficacy. No unknown is converted into a passing qualification.

Astra's qualification combines the bound offline declared Responses inventory
with actual local pipeline startup. The receipt explicitly says a live wire
inventory was not observed. Codex also declares three resource handlers:
`list_mcp_resources`, `list_mcp_resource_templates`, and `read_mcp_resource`.
They address the tools-only `cp_trial` server, which has no resources. V2 does
not claim exact seven-tool parity between complete vendor harnesses.

## Operational evidence, 2026-10-12

Thirteen local regression controls pass, including the original relative-path
startup failure, normalized relative-input startup for both providers in both
access modes, readonly write denial, unknown initialization, failed-server
initialization, unexpected tools, duplicate tools, resource-handler attribution, failed preflight stopping inference, and missing
live initialization remaining unknown and ineligible. These controls make zero hosted inference requests.

Reproduce:

```sh
python3 -B -m unittest discover \
  -s docs/research/2026-10-confidence/pr-benchmark \
  -p test_hybrid_v2.py -v
```

The operational replay has one expected RED relative-path control and four
GREEN absolute-path controls. Private receipts and actual subprocess
stdout/stderr are retained under `.confidence/benchmark/v2-path-qualification/`.
Their hashes are in `proof.json`; they contain no model reasoning. A separate
full staged non-task toy qualification is required before any V2 efficacy
cohort is frozen and launched.

## Limits

Discovery of seven tool names is not execution of every tool. The local checks
exercise transport, listing, and readonly enforcement. They do not establish
model availability, accuracy, account capacity, live API billing parity, or
containment of a descendant that detaches from its original process group.
Model calls and full staged toy results must be reported separately. V2 is
conditioned on observed failures in the first cohort and must be labeled
exploratory even though its own outcomes are not consulted before freezing.
