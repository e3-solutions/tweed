import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tweed_journal as journal  # noqa: E402


BASE = "1" * 40
COMMIT = "2" * 40
REPO = "/repo/tweed"
ISSUE = "TST-1"
RUN = "tw_0123456789abcdef"


def genesis(kind="feature"):
    stage = "needs-rca" if kind == "problem" else "needs-scope"
    return journal.build_genesis_description(
        {
            "schema_version": 1,
            "kind": kind,
            "stage": stage,
            "contract_revision": 0,
            "repository": REPO,
            "planning_base": BASE,
            "integration_branch": None,
            "integration_commit": None,
            "linear_project": "Test",
            "last_run": RUN,
        },
        "# Request\n\nShip naïve CSV",
    )


def add_record(description, comments, phase, report=None, run_id=RUN):
    snapshot = journal.validate_snapshot(
        description=description,
        comments=comments,
        issue_identifier=ISSUE,
        expected_repository=REPO,
        expected_base_commit=BASE,
    )
    report = report or f"Status: {journal.TRANSITIONS[phase][3]}\n\n{phase} report"
    predecessor = snapshot.records[-1].digest if snapshot.records else snapshot.genesis.digest
    record = journal.build_record(
        issue_identifier=ISSUE,
        run_id=run_id,
        phase=phase,
        status=journal.TRANSITIONS[phase][3],
        artifact_digest=journal.sha256_text(report),
        predecessor_digest=predecessor,
        genesis_digest=snapshot.genesis.digest,
        repository=REPO,
        base_commit=BASE,
        branch="arya/work" if phase in {"implement", "review"} else None,
        commit=COMMIT if phase in {"implement", "review"} else None,
        report=report,
    )
    return record


class JournalTests(unittest.TestCase):
    def test_construct_validate_and_materialize_complete_chain(self):
        description = genesis("problem")
        comments = []
        for phase in journal.PHASE_ORDER:
            record = add_record(description, comments, phase)
            self.assertRegex(record.metadata["comment_id"], journal.UUID4_RE)
            comments.append(record.comment)
        snapshot = journal.validate_snapshot(
            description=description,
            comments=comments,
            issue_identifier=ISSUE,
            expected_repository=REPO,
            expected_base_commit=BASE,
            expected_branch="arya/work",
            expected_commits={"implement": COMMIT, "review": COMMIT},
        )
        self.assertEqual(snapshot.stage, "ready-to-merge")
        view = journal.materialize_snapshot(snapshot)
        self.assertEqual(view["metadata"]["contract_revision"], 4)
        self.assertEqual(set(view["reports"]), {"rca", "scope", "implementation", "review"})
        self.assertIn("Ship naïve CSV", view["description"])

    def test_human_prose_and_nonjournal_comments_are_ignored(self):
        description = "Human intro\n\n" + genesis() + "\nHuman footer"
        record = add_record(description, [], "scope")
        snapshot = journal.validate_snapshot(
            description=description,
            comments=["ordinary discussion", record.comment, "more prose"],
            issue_identifier=ISSUE,
            expected_repository=REPO,
        )
        self.assertEqual(snapshot.stage, "ready-to-implement")

    def test_exact_duplicate_is_coalesced_and_conflicting_id_is_rejected(self):
        description = genesis()
        record = add_record(description, [], "scope")
        retry = add_record(description, [], "scope")
        self.assertEqual(retry.comment, record.comment)
        divergent_retry = add_record(description, [], "scope", "different report")
        self.assertEqual(
            divergent_retry.metadata["comment_id"], record.metadata["comment_id"]
        )
        self.assertNotEqual(divergent_retry.digest, record.digest)
        snapshot = journal.validate_snapshot(
            description=description,
            comments=[record.comment, record.comment],
            issue_identifier=ISSUE,
            expected_repository=REPO,
        )
        self.assertEqual(len(snapshot.records), 1)
        metadata = copy.deepcopy(record.metadata)
        changed_report = record.report + "!"
        metadata["artifact_digest"] = journal.sha256_text(changed_report)
        metadata["record_digest"] = journal._record_digest(metadata, changed_report)
        conflict = journal.build_comment(metadata, changed_report)
        with self.assertRaisesRegex(journal.JournalError, "conflicting duplicate"):
            journal.validate_snapshot(
                description=description,
                comments=[record.comment, conflict],
                issue_identifier=ISSUE,
                expected_repository=REPO,
            )

    def test_unique_run_phase_rejects_divergence_even_with_different_marker_id(self):
        description = genesis()
        record = add_record(description, [], "scope")
        metadata = copy.deepcopy(record.metadata)
        metadata["comment_id"] = journal.deterministic_comment_id("forged-other-id")
        metadata["record_digest"] = journal._record_digest(metadata, record.report)
        divergent_marker = journal.build_comment(metadata, record.report)
        with self.assertRaisesRegex(journal.JournalError, "duplicate run/phase"):
            journal.validate_snapshot(
                description=description,
                comments=[record.comment, divergent_marker],
                issue_identifier=ISSUE,
                expected_repository=REPO,
            )

    def test_frozen_head_detects_deleted_tail(self):
        description = genesis()
        scope = add_record(description, [], "scope")
        implementation = add_record(description, [scope.comment], "implement")
        with self.assertRaisesRegex(journal.JournalError, "frozen predecessor"):
            journal.validate_snapshot(
                description=description,
                comments=[scope.comment],
                issue_identifier=ISSUE,
                expected_repository=REPO,
                expected_head_digest=implementation.digest,
            )
        with self.assertRaisesRegex(journal.JournalError, "frozen stage"):
            journal.validate_snapshot(
                description=description,
                comments=[scope.comment],
                issue_identifier=ISSUE,
                expected_repository=REPO,
                expected_stage="ready-to-review",
            )

    def test_fork_dangling_and_illegal_transition_fail_closed(self):
        description = genesis()
        one = add_record(description, [], "scope", "one")
        two = add_record(
            description, [], "scope", "two", run_id="tw_1111111111111111"
        )
        with self.assertRaisesRegex(journal.JournalError, "fork"):
            journal.validate_snapshot(description=description, comments=[one.comment, two.comment], issue_identifier=ISSUE, expected_repository=REPO)
        dangling = journal.build_record(
            issue_identifier=ISSUE, run_id=RUN, phase="scope", status="scoped",
            artifact_digest=journal.sha256_text("x"), predecessor_digest="9" * 64,
            genesis_digest=journal.parse_genesis(description).digest, repository=REPO,
            base_commit=BASE, branch=None, commit=None, report="x",
        )
        with self.assertRaisesRegex(journal.JournalError, "dangling"):
            journal.validate_snapshot(description=description, comments=[dangling.comment], issue_identifier=ISSUE, expected_repository=REPO)
        implementation = journal.build_record(
            issue_identifier=ISSUE, run_id=RUN, phase="implement", status="implemented",
            artifact_digest=journal.sha256_text("x"), predecessor_digest=journal.parse_genesis(description).digest,
            genesis_digest=journal.parse_genesis(description).digest, repository=REPO,
            base_commit=BASE, branch="arya/work", commit=COMMIT, report="x",
        )
        with self.assertRaisesRegex(journal.JournalError, "illegal phase"):
            journal.validate_snapshot(description=description, comments=[implementation.comment], issue_identifier=ISSUE, expected_repository=REPO)

    def test_disconnected_cycle_is_rejected(self):
        # A hash cycle cannot be constructed through the public builder without a
        # preimage attack; exercise graph validation with already-parsed records.
        one = journal.Record(
            {"predecessor_digest": "b" * 64}, "one", "a" * 64, "one"
        )
        two = journal.Record(
            {"predecessor_digest": "a" * 64}, "two", "b" * 64, "two"
        )
        with self.assertRaisesRegex(journal.JournalError, "cycle"):
            journal._ordered_chain([one, two], "c" * 64)

    def test_protocol_tokens_bind_exact_request_report_and_envelope(self):
        description = genesis()
        parsed = journal.parse_genesis(description)
        normalized_description = description.replace("naïve", "naive")
        self.assertEqual(journal.parse_genesis(normalized_description).digest, parsed.digest)
        record = add_record(description, [], "scope", "Résumé\nline")
        for normalized in (
            record.comment.replace("Résumé\nline", "Resume line"),
            "prefix\n" + record.comment + "\nsuffix",
            record.comment.replace("\n\n`tweed-journal", "\r\n\r\n`tweed-journal"),
        ):
            self.assertEqual(journal.parse_comment(normalized).digest, record.digest)
        token_at = record.comment.index(journal.RECORD_TOKEN) + len(journal.RECORD_TOKEN)
        changed_token = record.comment[:token_at] + "A" + record.comment[token_at + 1 :]
        with self.assertRaises(journal.JournalError):
            journal.parse_comment(changed_token)

    def test_malformed_or_embedded_marker_fails_closed(self):
        description = genesis()
        record = add_record(description, [], "scope")
        token = record.comment[record.comment.index(journal.RECORD_TOKEN) :]
        for changed in (
            record.comment + "\n" + token,
            record.comment.replace(journal.RECORD_TOKEN, journal.RECORD_TOKEN + "!"),
            journal.RECORD_START,
        ):
            with self.assertRaises(journal.JournalError):
                journal.parse_comment(changed)

    def test_wrong_issue_repository_base_branch_and_commit_are_rejected(self):
        description = genesis()
        scope = add_record(description, [], "scope")
        implement = add_record(description, [scope.comment], "implement")
        cases = (
            {"issue_identifier": "OTHER"},
            {"expected_repository": "/other"},
            {"expected_base_commit": "3" * 40},
            {"expected_branch": "arya/other"},
            {"expected_commits": {"implement": "4" * 40}},
        )
        for overrides in cases:
            kwargs = dict(description=description, comments=[scope.comment, implement.comment], issue_identifier=ISSUE, expected_repository=REPO)
            kwargs.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(journal.JournalError):
                journal.validate_snapshot(**kwargs)

    def test_chain_rejects_divergent_base_and_branch_provenance(self):
        description = genesis()
        scope = add_record(description, [], "scope")
        implement = add_record(description, [scope.comment], "implement")
        changed = copy.deepcopy(implement.metadata)
        changed["base_commit"] = "3" * 40
        changed["record_digest"] = journal._record_digest(changed, implement.report)
        changed_base = journal.build_comment(changed, implement.report)
        with self.assertRaisesRegex(journal.JournalError, "base provenance"):
            journal.validate_snapshot(
                description=description,
                comments=[scope.comment, changed_base],
                issue_identifier=ISSUE,
                expected_repository=REPO,
            )
        review = add_record(description, [scope.comment, implement.comment], "review")
        changed = copy.deepcopy(review.metadata)
        changed["branch"] = "arya/other"
        changed["record_digest"] = journal._record_digest(changed, review.report)
        changed_branch = journal.build_comment(changed, review.report)
        with self.assertRaisesRegex(journal.JournalError, "branch provenance"):
            journal.validate_snapshot(
                description=description,
                comments=[scope.comment, implement.comment, changed_branch],
                issue_identifier=ISSUE,
                expected_repository=REPO,
            )

    def test_legacy_contiguous_prefix_is_adopted_but_inconsistent_legacy_fails(self):
        metadata = {
            "schema_version": 1, "kind": "feature", "stage": "ready-to-implement",
            "contract_revision": 1, "repository": REPO, "planning_base": BASE,
            "integration_branch": None, "integration_commit": None, "last_run": RUN,
        }
        metadata_json = json.dumps(metadata, indent=2, sort_keys=True)
        description = (
            f"{journal.META_START}\n## Tweed\n\n```json\n{metadata_json}\n```\n{journal.META_END}\n\n"
            "<!-- tweed:request:start -->\n# Request\n\nLegacy\n<!-- tweed:request:end -->\n\n"
            "<!-- tweed:scope:start -->\nStatus: scoped\n\nLegacy scope\n<!-- tweed:scope:end -->\n"
        )
        snapshot = journal.validate_snapshot(description=description, comments=[], issue_identifier=ISSUE, expected_repository=REPO)
        self.assertEqual(snapshot.stage, "ready-to-implement")
        self.assertTrue(snapshot.records[0].synthetic)
        broken = description.replace('"contract_revision": 1', '"contract_revision": 0')
        with self.assertRaisesRegex(journal.JournalError, "revision"):
            journal.validate_snapshot(description=broken, comments=[], issue_identifier=ISSUE, expected_repository=REPO)

        report = "Status: implemented\n\nFirst v2 implementation"
        appended = journal.build_record(
            issue_identifier=ISSUE,
            run_id=RUN,
            phase="implement",
            status="implemented",
            artifact_digest=journal.sha256_text(report),
            predecessor_digest=snapshot.records[-1].digest,
            genesis_digest=snapshot.genesis.digest,
            repository=REPO,
            base_commit=BASE,
            branch="arya/work",
            commit=COMMIT,
            report=report,
        )
        migrated = journal.validate_snapshot(
            description=description,
            comments=[appended.comment],
            issue_identifier=ISSUE,
            expected_repository=REPO,
        )
        self.assertEqual([item.metadata["phase"] for item in migrated.records], ["scope", "implement"])
        self.assertTrue(migrated.records[0].synthetic)
        self.assertFalse(migrated.records[1].synthetic)
        self.assertEqual(migrated.stage, "ready-to-review")

    def test_builder_rejects_illegal_status_and_missing_write_provenance(self):
        root = journal.parse_genesis(genesis()).digest
        kwargs = dict(
            issue_identifier=ISSUE, run_id=RUN, phase="scope", status="blocked",
            artifact_digest=journal.sha256_text("x"), predecessor_digest=root,
            genesis_digest=root, repository=REPO, base_commit=BASE,
            branch=None, commit=None, report="x",
        )
        with self.assertRaisesRegex(journal.JournalError, "illegal completed status"):
            journal.build_record(**kwargs)
        kwargs.update(phase="implement", status="implemented")
        with self.assertRaisesRegex(journal.JournalError, "requires branch"):
            journal.build_record(**kwargs)


if __name__ == "__main__":
    unittest.main()
