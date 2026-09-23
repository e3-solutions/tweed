# Independent review

Use this reference when the review gate in `SKILL.md` triggers. A review is useful when its findings can be checked, not when it is long.

## Who does what

- The reviewer reads, runs checks, and reports. It never edits tracked files; scratch files go outside the repository.
- The task owner fixes defects, decides every finding, and captures the proof.

## Brief the reviewer

Give each reviewer the change, the contract goal, the must-not-happen rules, and the captured run IDs with their log paths. Withhold the owner's self-assessment, evidence details, and other reviewers' findings until the reviewer reports. Independent first; comparison later.

Copy this brief and fill in the brackets:

```text
Role: independent reviewer. You work alone and have not seen the author's reasoning.
Do not modify tracked files; write scratch files only under [scratch directory].

Change: [diff command or PR]. Goal: [contract goal].
Must not happen: [contract must_not_happen].
Captured evidence: [run IDs and log paths]. Rerun only what you need to demonstrate a defect.

1. Contract: list what this change must not break, in at most 5 lines: public behavior,
   exit codes, error reporting, and promises in README, CHANGELOG, references, and docstrings.
2. Backward check: for each changed hunk, trace callers and callees toward those outcomes.
   Probe missing or malformed data, empty collections, non-finite numbers, special exit
   codes, signals, and exceptions raised midway.
3. Demonstrate: make each suspected defect checkable with a failing test or a short repro.
   Run it against the change and, when cheap, against its base.

Findings: only defects with a specific local failure, each with
- location: file:line
- trigger: concrete input or state
- expected vs actual
- proof: command and observed result, or "unverified: <why>"
- severity: high / medium / low
Observations: at most 3 unproven concerns, labeled as observations.
Not findings: style, naming, alternative designs, or hardening without a concrete trigger.
If there are no findings, say "No defects found" and list what you checked in at most 5 bullets.
```

## Decide every finding

- Judge each finding by its proof. Agreement between reviewers is not evidence; one reproduction outweighs several unsupported opinions.
- End every finding as `fixed` (capture the reproduction as a diagnostic run and the passing check as a supporting run), `refuted` (state the evidence), or `accepted risk` (also list it in `risks`). Record it in `review.findings`, for example: `fixed: validate crashes on a report without evidence (confidence.py:1246); runs repro-before, suite-after`.
- Settle disagreements with a captured run, not repeated argument. Do not drop a finding silently.

## Staff proportionally

- One capable reviewer with this brief is the default. Use the strongest available model for adversarial review; subtle defects often require cross-checking every call site and documented promise.
- Do not split one model into parallel narrow lanes by default. Separate lanes add cost, and a lane boundary can excuse a reviewer from reporting a defect it noticed.
- Critical work keeps separate roles: `test_designer` designs proof before implementation, and `adversarial_reviewer` reviews the change afterward. A different model family adds useful diversity when cost and data exposure are authorized; record which model reviewed.
