# Independent public production patch replay

**All 101 published patches reconstruct the production/helper projection of their independently graded private snapshots.** Each patch was applied byte-for-byte to a fresh copy of its correct frozen base, using Git 2.54.0 and `git apply --index --binary --allow-empty`. No whitespace repair, patch rewriting, task oracle or model call was used.

| Cohort | Scheduled assignments | Published patches replayed | Missing patch assignments |
| --- | ---: | ---: | ---: |
| Original seven-arm comparison | 84 | 82 / 82 | 2 interrupted |
| Invalid first mixed-provider block | 48 | 19 / 19 | 2 interrupted; 27 unstarted |
| Total | 132 | 101 / 101 | 31 |

The missing assignments retain their published unknown outcomes. They are outside the published-patch replay denominator; they do not disappear from the scheduled cohorts and are not scored as successful replays. No running V2 assignment is included in this audit.

For every available patch, the audit rechecked public patch hashes and bytes against the private submitted patch, raw/graded receipt bindings, current full candidate snapshot digest, correct base content digest and pinned curation digest. It then compared every allowed production path and any new root Python helper against the candidate: existence, exact bytes, executable mode and full permission bits. No unexpected staged path appeared. All 101 also match full permission bits in this particular corpus. Git represents executable modes, not every possible POSIX permission change; this result does not promise broader mode reconstruction.

Eleven patches are empty. They correctly reconstruct unchanged production projections and are retained as valid no-change artifacts; this says nothing about whether those unchanged submissions solve their tasks. Across production paths, there are 142 content modifications and 109 unchanged-file comparisons. The actual published corpus contains no production additions, deletions or executable-mode changes.

A separate non-task control covers addition of a Python file, deletion, binary content and an executable-mode change, all of which replay correctly. Its truncated negative is deliberately informative: with `--allow-empty`, Git accepts the first 16 bytes of a diff as no changes and returns exit zero. The candidate-projection verification rejects it because its contents and modes do not reconstruct the candidate. A successful Git process exit alone is insufficient proof of replay. These controls are separate from the 101 model-produced artifact denominator.

The reviewer authored the earlier publication exporter; that relationship is disclosed. The frozen production patch builder was authored separately and was not changed by this audit. This evidence supports artifact reproducibility, not task acceptance, whole-application behavior, model accuracy or proof-packet quality. Tests, generated proof packets, protocol copies, synthetic Git history and unrelated actor files lie outside the production/helper projection.

Reproduce the audit without inference or held-out oracle execution:

```sh
python3 -B docs/research/2026-10-confidence/pr-benchmark/replay_public_patches.py \
  --private-output .confidence/benchmark/patch-replay-audit.json
```

Source and all per-artifact findings are recorded in [PATCH-REPLAY-AUDIT.json](PATCH-REPLAY-AUDIT.json). The audit-script SHA256 is `31efc97c8260c0b2702600a5060a57d36cb9f577895d159b51cf4aecf6b89601`; the private audit SHA256 is `f95bb879f25b06fba33a75acc7235f4416ba41703bcd550aac48c2c1a83554ce`. The public JSON contains production-relative paths, digests and verification facts. It contains no model transcripts, candidate contents, private host paths or subprocess error prose.
