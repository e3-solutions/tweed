# Linear adapter contract

Set `TWEED_LINEAR_ADAPTER` to an executable configured through an officially
supported Linear authentication path. Tweed sends one UTF-8 JSON object on
standard input and accepts one UTF-8 JSON object on standard output. Both use
`"protocol":"dev.tweed.linear.v1"`.

The operations are `fetch`, `verify`, `create-or-recover`, and
`compare-and-swap`. Issue snapshots contain `identifier`, `url`, `title`,
`description`, opaque `revision`, and `digest`. `digest` is lowercase SHA-256
of the exact UTF-8 description bytes.

`compare-and-swap` receives the expected revision, digest, and complete
description plus the desired description and digest. It may return `applied`,
`already-applied`, or `stale`. `applied` is valid only when the authoritative
revision, digest, and bytes were checked atomically with the write. A connector
that can only read and then update must return an error; it must not claim CAS.
`stale` must perform no write and may include the current snapshot for
idempotent formatting reconciliation.

The adapter must not emit credentials or logs on standard output. Tweed passes
no ambient credential values in requests and does not discover or repurpose
credentials. The hermetic adapter in `tests/fake_linear_adapter.py` is a
protocol fixture, not a production authentication implementation.
