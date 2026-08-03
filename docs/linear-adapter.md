# Linear journal adapter

Tweed bundles `tweed_linear_adapter.py`, a standard-library client for the fixed
`https://api.linear.app/graphql` endpoint. For this local personal tool, export a
personal key at runtime:

```sh
export LINEAR_API_KEY=...
```

Linear documents personal API keys as the easiest authentication method for
personal scripts and requires the raw key in the `Authorization` header. OAuth2
remains the appropriate choice for applications used by others. The adapter
never discovers credentials, puts the key in argv or JSON, reflects GraphQL
messages/bodies/headers, or follows redirects. See [Linear GraphQL authentication
and error handling](https://linear.app/developers/graphql).
The parent blanks the key and adapter override in every Codex/model child
environment, so repository code and model-invoked commands cannot access Linear
authentication.

## Protocol and journal

The runner and adapter exchange one bounded UTF-8 JSON object on standard input
and output using `"protocol":"dev.tweed.linear.v2"`. Operations are `fetch`,
`verify`, `create-or-recover`, and `append-or-recover`. `TWEED_LINEAR_ADAPTER`
may override the bundled executable for hermetic testing or a compatible
installation; it is not required in production.

The issue description is written only at intake. It keeps the visible original
request and a canonical base64url protocol token containing the exact UTF-8
request and genesis metadata. Each successful phase is one top-level,
human-readable comment whose token contains the exact report bytes and canonical
`dev.tweed.linear-journal.v2` envelope. This survives Linear's documented
Markdown/ProseMirror normalization without treating formatting as a new
reasoning problem. The envelope and report are SHA-256 bound to a unique
predecessor. A complete paginated read must form exactly one legal chain.
Ordinary human comments and prose outside protocol tokens are ignored; token
changes, edited/archived records, malformed tokens, bad hashes, dangling
predecessors, conflicting duplicates, and forks fail closed.

Issue and comment mutations use deterministic caller-supplied UUID-v4-shaped
IDs. After any ambiguous network or GraphQL outcome, the adapter queries that
exact ID and accepts only the expected semantic protocol digest, issue identity,
and complete validated chain. It never blindly repeats a mutation. Exact-ID
absence probes use bounded collection queries because Linear's singular issue
and comment fields are non-null. Comment pagination, individual and aggregate body bytes,
requests, responses, pages, and timeouts are bounded during streaming capture;
an overflowing child is terminated. GraphQL `errors` fail even
on HTTP 200; rate-limit failures are redacted and left retryable. Linear's
[pagination](https://linear.app/developers/pagination) and [rate-limit
guidance](https://linear.app/developers/rate-limiting) are followed.

## Concurrency limit

The [published Linear schema](https://github.com/linear/linear/blob/7ef4c5024f88667b2c85057ff4c905676c4a93c2/packages/sdk/src/schema.graphql)
exposes ordinary `issueUpdate` and `commentCreate` mutations without a version or
predecessor precondition. Tweed therefore does not claim authoritative atomic
CAS. It preflights the frozen head, appends once, and validates the whole chain
again. Concurrent cross-host siblings become a visible fork and block every
later phase; local issue/run locks prevent same-host duplication.

Linear comments can be edited or deleted. Tweed detects edits, archives,
missing interior records, and deletion relative to a persisted frozen head. A
fresh client cannot prove that a now-deleted tail once existed because the
documented public API provides no independent immutable head anchor. This limit
is explicit rather than hidden behind an impossible CAS claim.
