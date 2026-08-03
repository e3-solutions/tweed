# Linear journal adapter

Tweed bundles `tweed_linear_adapter.py`, a standard-library client for the fixed
`https://api.linear.app/graphql` endpoint. Its default authentication is Linear's
first-party OAuth2 authorization-code flow with PKCE S256.

```sh
tweed auth login --client-id YOUR_LINEAR_OAUTH_CLIENT_ID
```

Provision the application once from Linear settings using
[`linear-oauth-app.json`](../linear-oauth-app.json). The registered callback must
be exactly `http://localhost:43817/oauth/callback`; no client secret is used or
stored. Login uses independent random state and verifier values, PKCE S256, an
exact loopback callback, bounded waits, and the least-privilege
`read,issues:create,comments:create` scopes. `--manual` supports environments
where the browser cannot complete the loopback redirect.

Tokens are stored outside repositories and run artifacts in the operating-system
credential manager. Each complete record is written to the inactive one of two
deterministic keyring slots before an owner-only nonsecret pointer is atomically
switched; the same canonical state directory holds cross-process locks. Inactive
cleanup is strict and retryable because both slot names remain discoverable. This
prevents an in-place keyring overwrite from destroying the last recoverable
refresh pair or orphaning an unknown token record. Setting
`TWEED_LINEAR_OAUTH_FILE` explicitly selects a `0700`/`0600` file
backend for hermetic tests or headless systems with an independently enforced
filesystem boundary. Refresh operations are serialized with `flock`; the
complete rotated token pair is atomically persisted. A write-ahead refresh marker
permits exact replay only inside a conservative portion of Linear's documented
30-minute lost-response grace. `tweed auth logout` attempts revocation at Linear
before removing local tokens and reports when remote revocation was not confirmed.
See [Linear OAuth2](https://linear.app/developers/oauth-2-0-authentication) and
[GraphQL authentication](https://linear.app/developers/graphql).

API-key authentication is retained only when explicitly selected with
`TWEED_LINEAR_AUTH=api-key` and `LINEAR_API_KEY`. External
`TWEED_LINEAR_ADAPTER` processes receive no Tweed credentials. The configured
`linear` MCP server and known credential environment variables are disabled in
every Codex/model child. These controls prevent Tweed from forwarding credentials;
they do not claim to sandbox arbitrary same-user code from an unlocked OS keyring.

## Protocol and journal

The runner and adapter exchange one bounded UTF-8 JSON object on standard input
and output using `"protocol":"dev.tweed.linear.v2"`. Operations are `fetch`,
`verify`, `create-or-recover`, and `append-or-recover`. `TWEED_LINEAR_ADAPTER`
may override the bundled executable for hermetic testing or a compatible
installation; it is not required in production.

The hosted Linear MCP tool surface is not a journal transport fallback. Its
current creates have no caller-assigned IDs or idempotency keys, and comment
reads omit archived-inclusive edit/archive state. Those gaps would weaken exact
ambiguous-write recovery and fail-closed journal validation.

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
