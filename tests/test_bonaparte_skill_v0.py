import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "bonaparte"
BASE_FIELDS = {
    "request",
    "phase",
    "repository",
    "HEAD",
    "raw-constraints",
    "ambient-manifest",
}


def phase_matrix(skill):
    section = skill.split("## Phase entry contract", 1)[1].split(
        "## Operating boundaries", 1
    )[0]
    rows = {}
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "Phase |" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows[cells[0]] = set(re.findall(r"`([^`]+)`", cells[1]))
    return rows


class ProtocolScenario:
    """Small executable model of the skill's ordering and invalidation gates."""

    def __init__(self, max_live, review_only=False, workspace=None):
        self.max_live = max_live
        self.review_only = review_only
        self.workspace = dict(workspace or {})
        self.live = set()
        self.proof_accepted = False
        self.task_manifest = None
        self.ambient_manifest = None
        self.review_verdicts = set()

    @staticmethod
    def admits(required, supplied):
        return required <= supplied

    def spawn(self, role):
        if role == "writer" and self.review_only:
            raise RuntimeError("review-only is immutable")
        if role == "writer" and not self.proof_accepted:
            raise RuntimeError("proof must precede writer")
        if len(self.live) >= self.max_live:
            raise RuntimeError("concurrency cap")
        self.live.add(role)

    def finish(self, role):
        self.live.remove(role)

    def accept_proof(self):
        self.proof_accepted = True

    def freeze(self, task_manifest, ambient_manifest):
        self.task_manifest = dict(task_manifest)
        self.ambient_manifest = dict(ambient_manifest)
        self.review_verdicts.clear()

    def record_review(self, lens):
        self.review_verdicts.add(lens)

    def correct(self, task_manifest):
        if self.review_only:
            raise RuntimeError("review-only is immutable")
        self.task_manifest = dict(task_manifest)
        self.review_verdicts.clear()

    def post_commit_matches(self, committed_task, current_ambient):
        return (
            committed_task == self.task_manifest
            and current_ambient == self.ambient_manifest
        )


class BonaparteSkillV0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (SKILL_DIR / "SKILL.md").read_text()
        cls.one_line = " ".join(cls.skill.split())
        cls.metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text()
        cls.entries = phase_matrix(cls.skill)
        cls.max_live = int(
            re.search(r"Spawn no more than `(\d+)`", cls.skill).group(1)
        )

    def test_is_an_instruction_only_skill(self):
        files = {
            path.relative_to(SKILL_DIR).as_posix()
            for path in SKILL_DIR.rglob("*")
            if path.is_file()
        }
        self.assertEqual(files, {"SKILL.md", "agents/openai.yaml"})
        for forbidden in ("BONAPARTE_", "resume_token", "Invoke the bare `bonaparte`"):
            self.assertNotIn(forbidden, self.skill)

    def test_description_has_positive_and_negative_triggers(self):
        frontmatter = self.skill.split("---", 2)[1]
        self.assertIn("run Bonaparte", frontmatter)
        self.assertIn("turn a Linear issue into a reviewed PR", frontmatter)
        self.assertIn("Do not use for a review-only request", frontmatter)

    def test_phase_matrix_is_complete_and_non_circular(self):
        self.assertEqual(
            set(self.entries),
            {
                "Record / intake",
                "Bug investigation",
                "Feature investigation",
                "Scope",
                "Implementation",
                "Review",
                "Delivery",
            },
        )
        self.assertNotIn("bug-rca", self.entries["Bug investigation"])
        self.assertIn("bug-rca", self.entries["Scope"])
        self.assertIn("task-manifest", self.entries["Review"])
        self.assertIn("review-verdicts", self.entries["Delivery"])

    def test_feature_investigation_can_start_from_raw_facts(self):
        supplied = BASE_FIELDS | {"requested-outcome", "current-limitation"}
        required = BASE_FIELDS | self.entries["Feature investigation"]
        self.assertTrue(ProtocolScenario.admits(required, supplied))

    def test_scope_and_review_block_incomplete_handoffs(self):
        raw_only = BASE_FIELDS | self.entries["Feature investigation"]
        self.assertFalse(
            ProtocolScenario.admits(BASE_FIELDS | self.entries["Scope"], raw_only)
        )
        scope_only = BASE_FIELDS | self.entries["Implementation"]
        self.assertFalse(
            ProtocolScenario.admits(BASE_FIELDS | self.entries["Review"], scope_only)
        )

    def test_decision_frontier_and_context_isolation_are_hard_gates(self):
        for text in (
            "write its **decision frontier**",
            "Every frontier question requires an evidence-bearing",
            "Use zero subagents only for a fully mechanical",
            "spawn with no inherited conversation turns",
            "do not imply statistical independence",
            "A failed spawn, missing agent ID, or empty wait target",
        ):
            self.assertIn(text, self.one_line)

    def test_adaptive_topology_has_symmetric_up_and_down_routes(self):
        for text in (
            "conservative Bonaparte assurance defaults",
            "not research-established universal optima",
            "One context-isolated investigator plus a direct reproduction may suffice",
            "The challenger is never omitted",
            "One may suffice for a local low-risk diff",
            "do not retain or add an LLM seat merely to satisfy headcount",
        ):
            self.assertIn(text, self.one_line)

    def test_concurrency_cap_is_executable(self):
        scenario = ProtocolScenario(self.max_live)
        for role in ("investigator", "falsifier", "reproducer"):
            scenario.spawn(role)
        with self.assertRaisesRegex(RuntimeError, "concurrency cap"):
            scenario.spawn("extra")

    def test_proof_artifact_must_precede_writer(self):
        scenario = ProtocolScenario(self.max_live)
        with self.assertRaisesRegex(RuntimeError, "proof must precede writer"):
            scenario.spawn("writer")
        scenario.accept_proof()
        scenario.spawn("writer")
        self.assertIn("writer", scenario.live)
        self.assertLess(
            self.skill.index("accept a **proof artifact**"),
            self.skill.index("Only then give a separate writer"),
        )

    def test_review_only_cannot_spawn_writer_or_mutate(self):
        workspace = {"service.py": "candidate"}
        scenario = ProtocolScenario(self.max_live, review_only=True, workspace=workspace)
        scenario.accept_proof()
        scenario.freeze({"service.py": "candidate"}, {"notes.txt": "user"})
        with self.assertRaisesRegex(RuntimeError, "review-only is immutable"):
            scenario.spawn("writer")
        with self.assertRaisesRegex(RuntimeError, "review-only is immutable"):
            scenario.correct({"service.py": "changed"})
        self.assertEqual(scenario.workspace, workspace)
        self.assertIn("For a review-only request, do not edit, spawn a writer", self.one_line)

    def test_correction_invalidates_all_routed_review_credit(self):
        scenario = ProtocolScenario(self.max_live)
        scenario.freeze({"service.py": "v1"}, {"notes.txt": "user"})
        scenario.record_review("contract")
        scenario.record_review("correctness")
        self.assertEqual(len(scenario.review_verdicts), 2)
        scenario.correct({"service.py": "v2"})
        self.assertEqual(scenario.review_verdicts, set())
        self.assertIn("invalidates all routed reviewer verdicts", self.one_line)

    def test_task_and_ambient_manifests_are_separate_proofs(self):
        scenario = ProtocolScenario(self.max_live)
        task = {"service.py": ("hash-a", "100644")}
        ambient = {"notes.txt": ("hash-user", "100644")}
        scenario.freeze(task, ambient)
        self.assertTrue(scenario.post_commit_matches(task, ambient))
        self.assertFalse(
            scenario.post_commit_matches(task, {"notes.txt": ("changed", "100644")})
        )
        for text in (
            "**Task manifest:**",
            "**Ambient manifest:**",
            "Ambient work never enters the reviewed task diff or commit",
            "separately prove all ambient staged, unstaged, and untracked paths",
        ):
            self.assertIn(text, self.one_line)

    def test_dependency_impact_is_planned_and_replanned(self):
        for text in (
            "**Dependency/change-impact graph:**",
            "affected consumers, interface/data/control edges",
            "After any interface-affecting edit, re-evaluate",
        ):
            self.assertIn(text, self.one_line)

    def test_disagreement_uses_evidence_not_votes(self):
        for text in (
            "A vote or calibrated confidence may route the next diagnostic",
            "cannot establish software correctness",
            "Run the smallest discriminating diagnostic",
            "do not broadcast transcripts or invite open-ended group discussion",
            "three finding-bearing rounds as an operational ceiling",
        ):
            self.assertIn(text, self.one_line)

    def test_writer_reviewer_separation_and_exact_candidate(self):
        for text in (
            "a writer may not review its own change",
            "one fresh, non-author, read-only whole-diff reviewer",
            "exact task manifest, complete task-only diff",
            "Do not give them the author's conclusions",
            "final candidate state—not an earlier patch—was reviewed",
        ):
            self.assertIn(text, self.one_line)

    def test_phase_stop_boundaries_and_safety_remain_explicit(self):
        for text in (
            "Stop here for a record-only request.",
            "Stop here for an investigation-only request.",
            "Stop here for a scope-only request.",
            "Stop here for a review-only request.",
            "Never reset, clean, discard, overwrite, or stash unrelated changes",
            "Never force-push",
            "Do not create duplicates",
        ):
            self.assertIn(text, self.one_line)

    def test_ui_metadata_matches_skill(self):
        self.assertIn('display_name: "Bonaparte"', self.metadata)
        self.assertIn("$bonaparte", self.metadata)
        self.assertIn('value: "linear"', self.metadata)
        self.assertIn("allow_implicit_invocation: true", self.metadata)


if __name__ == "__main__":
    unittest.main()
