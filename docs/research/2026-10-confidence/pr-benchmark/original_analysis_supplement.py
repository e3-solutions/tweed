#!/usr/bin/env python3
"""Descriptive supplement; never rewrites registered scores or imputes outcomes."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

BASELINE = "original_cp_05"


def verified_acceptance(row):
    return row.get("passed") is True and row.get("harness_invalid") is not True


def terminal_closed(row):
    # A final declaration is observed; independent packet sufficiency is not.
    return (verified_acceptance(row) and row.get("declared_complete") is True
            and isinstance(row.get("remaining"), list) and row["remaining"] == [])


def key(row):
    return row["task_id"], row["arm_id"], row["repeat"]


def analyze(rows, schedule, interrupted_ids, secondary=None):
    indexed = {key(row): row for row in rows}
    expected = {key(row): row for row in schedule}
    if len(indexed) != len(rows) or len(expected) != len(schedule):
        raise ValueError("Duplicate observed or scheduled identity")
    if set(indexed) != set(expected):
        raise ValueError("Scheduled denominator/identities differ")
    for identity, row in indexed.items():
        if row["trial_id"] != expected[identity]["trial_id"]:
            raise ValueError("Trial ID differs from schedule")
        if row.get("passed") is not None and type(row["passed"]) is not bool:
            raise ValueError("Acceptance must be boolean or unknown")
    unknown = {row["trial_id"] for row in rows if row.get("passed") is None}
    if unknown != set(interrupted_ids):
        raise ValueError("Unknown outcomes differ from closed interruption inventory")
    if any(row.get("proof_packet_grade") is not None for row in rows):
        raise ValueError("Proof-packet sufficiency cannot be described as unassessed")
    by_arm = defaultdict(list)
    for row in rows:
        by_arm[row["arm_id"]].append(row)
    tasks = sorted({row["task_id"] for row in rows})
    repeats = sorted({row["repeat"] for row in rows})
    if repeats != [1, 2]:
        raise ValueError("Supplement requires two registered repeats")
    if len(rows) != len(tasks) * len(by_arm) * 2 or BASELINE not in by_arm:
        raise ValueError("Incomplete registered factorial design")
    arms = {}
    for name, arm_rows in sorted(by_arm.items()):
        count = len(arm_rows)
        accepted = sum(verified_acceptance(row) for row in arm_rows)
        closed = sum(terminal_closed(row) for row in arm_rows)
        missing = sum(row["trial_id"] in unknown for row in arm_rows)
        arms[name] = {
            "scheduled": count, "observed_receipts": count - missing,
            "verified_acceptance_lower_bound_count": accepted,
            "verified_acceptance_identification_count_bounds": [accepted, accepted + missing],
            "verified_acceptance_identification_rate_bounds": [accepted / count, (accepted + missing) / count],
            "terminal_closed_lower_bound_count": closed,
            "terminal_closed_identification_count_bounds": [closed, closed + missing],
            "terminal_closed_identification_rate_bounds": [closed / count, (closed + missing) / count],
            "interrupted_unknown_count": missing,
            "completion_declaration_unknown_count": sum(row.get("declared_complete") is None for row in arm_rows),
            "harness_invalid_count": sum(row.get("harness_invalid") is True for row in arm_rows),
        }
    baseline = arms[BASELINE]
    for name, values in arms.items():
        if name == BASELINE:
            continue
        for metric in ("verified_acceptance", "terminal_closed"):
            lower, upper = values[metric + "_identification_rate_bounds"]
            base_lower, base_upper = baseline[metric + "_identification_rate_bounds"]
            values[metric + "_delta_identification_bounds_vs_original"] = [lower - base_upper, upper - base_lower]
        pairs = []
        excluded = []
        for task in tasks:
            for repeat in repeats:
                baseline_row = indexed[(task, BASELINE, repeat)]
                alternative_row = indexed[(task, name, repeat)]
                if any(type(row.get("passed")) is not bool for row in (baseline_row, alternative_row)):
                    excluded.append({"task_id": task, "repeat": repeat})
                    continue
                pairs.append((task, baseline_row, alternative_row))
        task_deltas = defaultdict(list)
        trial_wins = trial_losses = 0
        for task, baseline_row, alternative_row in pairs:
            delta = int(verified_acceptance(alternative_row)) - int(verified_acceptance(baseline_row))
            task_deltas[task].append(delta)
            trial_wins += delta > 0
            trial_losses += delta < 0
        means = {task: statistics.mean(deltas) for task, deltas in task_deltas.items()}
        values["complete_pair_secondary"] = {
            "matched_trial_pairs": len(pairs), "excluded_unknown_pairs": excluded,
            "task_clusters": len(means), "pairs_per_task": {task: len(deltas) for task, deltas in task_deltas.items()},
            "accepted_baseline": sum(verified_acceptance(base) for _, base, _ in pairs),
            "accepted_alternative": sum(verified_acceptance(alt) for _, _, alt in pairs),
            "terminal_closed_baseline": sum(terminal_closed(base) for _, base, _ in pairs),
            "terminal_closed_alternative": sum(terminal_closed(alt) for _, _, alt in pairs),
            "trial_wins": trial_wins, "trial_losses": trial_losses,
            "trial_ties": len(pairs) - trial_wins - trial_losses,
            "task_acceptance_deltas": means,
            "mean_task_acceptance_delta": statistics.mean(means.values()) if means else None,
        }
    retrospective = []
    for task, audit_rows in sorted((secondary or {}).items()):
        primary = {row["trial_id"]: row for row in rows if row["task_id"] == task}
        audits = {row["trial_id"]: row for row in audit_rows}
        if len(audits) != len(audit_rows) or set(audits) != set(primary):
            raise ValueError("Secondary audit must cover every scheduled task identity")
        if any(type(row.get("oracle_passed")) is not bool for row in audit_rows):
            raise ValueError("Secondary audit still contains unknown outcomes")
        retrospective.append({
            "task_id": task, "scheduled": len(primary),
            "registered_oracle_acceptances": sum(row.get("oracle_passed") is True for row in primary.values()),
            "retrospective_workflow_acceptances": sum(row["oracle_passed"] for row in audits.values()),
            "changed_identities": [{"trial_id": identity, "registered_oracle_passed": primary[identity].get("oracle_passed"),
                "retrospective_workflow_passed": audits[identity]["oracle_passed"]} for identity in sorted(primary)
                if primary[identity].get("oracle_passed") != audits[identity]["oracle_passed"]],
            "classification": "Posthoc separate workflow audit; original scores unchanged; no efficacy inference",
        })
    return {"schema_version": 1, "classification": "Posthoc descriptive supplement to unchanged registered analysis",
        "baseline": BASELINE, "scheduled": len(rows), "independent_task_clusters": len(tasks),
        "repeats_per_task_arm": 2, "observed_receipts": len(rows) - len(unknown),
        "interrupted_unknown_ids": sorted(unknown), "arms": arms,
        "retrospective_workflow_audits": retrospective,
        "definitions": {
            "verified_acceptance_lower_bound": "passed=true and harness_invalid is not true; unknowns remain null in inputs, contribute no observed verified acceptance",
            "terminal_closed": "Verified acceptance AND observed declared_complete=true AND remaining is exactly []; this assesses a final declaration, not independent proof-packet sufficiency or all peer-call closure",
            "complete_pair_secondary": "Retain matched task/repeat pairs only when BOTH primary passed fields are boolean. Observed invalid-harness receipts stay nonsuccesses; unknown pairs are excluded. Average repeated-pair differences within each task, then weight retained task clusters equally",
            "identification_bounds": "Each externally interrupted missing outcome may be 0 or 1, without filling any input field. Bounds are marginal logically possible rates/deltas, not confidence intervals or probabilities. Timeouts with recorded missing final declarations do not acquire a fabricated declaration",
            "proof_packet_sufficiency": "Unassessed; proof_packet_grade remains null. Passing an oracle or receiving a complete declaration does not establish all protocol proof obligations",
        },
        "limitations": ["Six selected historical PR tasks from one repository; not a general efficacy estimate",
            "Repeated attempts do not add independent task clusters", "External interruption may bias observed lower-bound arm deltas",
            "Workflow audits were designed after observations and are reported separately without rescoring",
            "No hypothesis tests or causal improvement claim; complete-case selection and temporal service drift remain limitations"]}


def markdown(report):
    lines = ["# Original study descriptive supplement", "",
        "The registered analysis is unchanged. These results separate accepted artifacts from accepted artifacts with a complete final declaration and no listed gaps. All 84 scheduled trials remain visible; two external interruptions stay unknown.", "",
        "| Arm | Accepted artifacts /12 | Accepted + complete declaration /12 | Unknown interrupted | Acceptance possible range |",
        "|---|---:|---:|---:|---:|"]
    for arm, values in report["arms"].items():
        lo, hi = values["verified_acceptance_identification_count_bounds"]
        lines.append(f"| {arm} | {values['verified_acceptance_lower_bound_count']}/12 | {values['terminal_closed_lower_bound_count']}/12 | {values['interrupted_unknown_count']} | {lo}–{hi}/12 |")
    lines += ["", "Unknown interrupted outcomes are not observed failures. The ranges assign only logically possible 0/1 outcomes to the missing records; they are not imputed scores, probabilities, or confidence intervals. A positive observed alternative-minus-baseline delta can shrink by 8.33 percentage points if the missing original outcome would have passed. Both bounded-repair and original have one unknown, allowing their difference to shift in either direction.", "",
        "The stronger declaration metric requires scope-valid acceptance, valid harness metadata, `declared_complete=true`, and exactly `remaining=[]`. It does not establish that every proof packet or peer call completed; proof-packet sufficiency remains unassessed.", "",
        "Complete-pair secondary comparisons exclude a task/repeat pair only when either primary acceptance field is unknown. They preserve observed harness-invalid nonsuccesses, average repeat differences within each task, and then weight the six task clusters equally. Each alternative has 11 complete pairs; PR35 contributes one repeat, and the other tasks contribute two. This selected complete-case view is descriptive. Its available-repeat task mean is a different quantity from the fixed 12-trial identification bounds, so their numerical values must not be treated as interchangeable estimates.", "",
        "| Alternative | Complete pairs | Available-repeat mean task delta | Fixed 12-trial delta identification bounds |",
        "|---|---:|---:|---:|"]
    for arm, values in report["arms"].items():
        if arm == BASELINE:
            continue
        pairs = values["complete_pair_secondary"]
        lower, upper = values["verified_acceptance_delta_identification_bounds_vs_original"]
        lines.append(f"| {arm} | {pairs['matched_trial_pairs']} | {100 * pairs['mean_task_acceptance_delta']:+.2f} pp | {100 * lower:+.2f} to {100 * upper:+.2f} pp |")
    lines += ["",
        "| Separate posthoc workflow audit | Registered oracle | Workflow audit |",
        "|---|---:|---:|"]
    for audit in report["retrospective_workflow_audits"]:
        lines.append(f"| {audit['task_id']} | {audit['registered_oracle_acceptances']}/{audit['scheduled']} | {audit['retrospective_workflow_acceptances']}/{audit['scheduled']} |")
    lines += ["", "These workflow audits were developed after observations and cover all 14 identities for each audited task. They diagnose comparator limitations and do not replace original scores or prove protocol efficacy. See the separate workflow and budget/resume audit reports for their behavioral scope.", "",
        "Exact input file hashes, complete-pair counts/differences, missing-outcome bounds, changed workflow-audit identities, and definitions are recorded in `ORIGINAL-ANALYSIS-SUPPLEMENT.json`. The six historical PR clusters and two repeats do not justify a general claim of increased accuracy or autonomy.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--registered-analysis", type=Path, required=True)
    parser.add_argument("--interruption-audit", type=Path, required=True)
    parser.add_argument("--workflow-audit", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text())
    audit = read(args.interruption_audit)
    if not audit.get("passed") or audit.get("scheduled") != 84 or audit.get("graded_receipts") != 82:
        raise ValueError("Expected completed independently audited original82/84 inventory")
    secondary = {}
    inputs = {"normalized_receipts": args.receipts, "schedule": args.schedule,
        "unchanged_registered_analysis": args.registered_analysis, "interruption_audit": args.interruption_audit}
    for path in args.workflow_audit:
        rows = read(path)
        tasks = {row["task_id"] for row in rows}
        if len(tasks) != 1:
            raise ValueError("Workflow audit must contain exactly one task")
        task = next(iter(tasks))
        if task in secondary:
            raise ValueError("Duplicate workflow audit task")
        secondary[task] = rows
        inputs["retrospective_workflow_audit_" + task] = path
    report = analyze(read(args.receipts), read(args.schedule), audit["interrupted_unknown_ids"], secondary)
    if report["scheduled"] != 84 or report["independent_task_clusters"] != 6 or len(report["arms"]) != 7:
        raise ValueError("Original design differs from84 trials/6 tasks/7 arms")
    registered = read(args.registered_analysis)
    for arm, values in report["arms"].items():
        if registered["arms"][arm]["passed"] != values["verified_acceptance_lower_bound_count"]:
            raise ValueError("Supplement acceptance disagrees with registered analysis")
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["input_file_sha256"] = {label: hashlib.sha256(path.read_bytes()).hexdigest() for label, path in inputs.items()}
    report["supplement_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.markdown.write_text(markdown(report))


if __name__ == "__main__":
    main()
