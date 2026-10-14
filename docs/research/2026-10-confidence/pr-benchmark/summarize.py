#!/usr/bin/env python3
"""Paired, task-clustered descriptive analysis of PR replay receipts.

Input is a JSON array of normalized receipts. Never treats repeated attempts at
one PR as independent tasks. Missing costs/completion declarations stay missing.
"""
import argparse
import itertools
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def percentile(values, fraction):
    ordered = sorted(values)
    # Inverse empirical CDF: preserve discrete bootstrap mass at the endpoints.
    position = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[position]


def cluster_interval(task_deltas):
    """Exact empirical bootstrap of task means; small-N descriptive interval."""
    if not task_deltas:
        return None
    n = len(task_deltas)
    if n > 7:
        raise ValueError("Exact enumeration supports at most seven task clusters")
    samples = [statistics.mean(sample) for sample in itertools.product(task_deltas, repeat=n)]
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def aggregate(rows):
    costs = [r['total_cost_usd'] for r in rows if r.get('total_cost_usd') is not None]
    durations = [r['wall_seconds'] for r in rows if r.get('wall_seconds') is not None]
    declared = [r for r in rows if r.get('declared_complete') is True]
    successes = [r for r in rows if succeeded(r)]
    return {
        'attempts': len(rows), 'passed': len(successes),
        'oracle_passed_including_invalid': sum(r.get('passed') is True for r in rows),
        'success_rate': len(successes) / len(rows) if rows else None,
        'harness_invalid': sum(r.get('harness_invalid') is True for r in rows),
        'declared_complete': len(declared),
        'false_completion': sum(r.get('passed') is False for r in declared),
        'grading_unknown': sum(r.get('passed') is None for r in rows),
        'receipts_missing': sum(r.get('status') == 'missing_receipt' for r in rows),
        'completion_unknown': sum(r.get('declared_complete') is None for r in rows),
        'total_known_cost_usd': sum(costs), 'cost_unknown': len(rows) - len(costs),
        'mean_known_cost_usd': statistics.mean(costs) if costs else None,
        'mean_wall_seconds': statistics.mean(durations) if durations else None,
        'median_wall_seconds': statistics.median(durations) if durations else None,
        'autonomous_successes': sum(r.get('human_interventions') == 0 for r in successes),
        'interventions_unknown': sum(r.get('human_interventions') is None for r in rows),
        'denials': sum(r.get('denials', 0) for r in rows),
    }


def succeeded(row):
    return row.get('passed') is True and row.get('harness_invalid') is not True


def analyze(rows, baseline='original_cp_05', expected=None):
    keyed = {}
    by_arm = defaultdict(list)
    for row in rows:
        key = (row['task_id'], row['arm_id'], row['repeat'])
        if key in keyed:
            raise ValueError(f'Duplicate trial identity: {key}')
        keyed[key] = row
    if expected is not None:
        scheduled = {(r['task_id'], r['arm_id'], r['repeat']) for r in expected}
        if len(scheduled) != len(expected):
            raise ValueError('Duplicate scheduled trial identities')
        if set(keyed) - scheduled:
            raise ValueError('Receipt outside frozen schedule')
        for task, arm, repeat in scheduled - set(keyed):
            keyed[(task, arm, repeat)] = dict(task_id=task, arm_id=arm, repeat=repeat,
                status='missing_receipt', passed=None, declared_complete=None,
                total_cost_usd=None, wall_seconds=None, human_interventions=None)
    for row in keyed.values():
        by_arm[row['arm_id']].append(row)
    if baseline not in by_arm:
        raise ValueError('Baseline has no receipts')
    output = {'baseline': baseline, 'arms': {}, 'scheduled_trials': len(expected) if expected is not None else None,
        'observed_receipts': len(rows), 'limitations': [
        'Repeated trials are clustered by PR; they do not enlarge the independent task count.',
        'Bootstrap intervals are descriptive on a small selected task set, not a population efficacy guarantee.',
        'Missing cost is not treated as zero; harness-invalid and unfinished runs remain in attempt denominators.',
        'Passing a held-out oracle does not prove all behavior correct or eliminate possible training contamination.',
    ]}
    for arm, arm_rows in sorted(by_arm.items()):
        result = aggregate(arm_rows)
        task_deltas = defaultdict(list)
        false_deltas = defaultdict(list)
        cost_deltas = defaultdict(list)
        time_deltas = defaultdict(list)
        wins = losses = ties = missing = 0
        for row in arm_rows:
            control = keyed.get((row['task_id'], baseline, row['repeat']))
            if control is None:
                missing += 1
                continue
            delta = int(succeeded(row)) - int(succeeded(control))
            task_deltas[row['task_id']].append(delta)
            # Missing declarations are unknown, not truthful partial reports.
            if (row.get('declared_complete') is not None and control.get('declared_complete') is not None
                    and row.get('passed') is not None and control.get('passed') is not None):
                false_deltas[row['task_id']].append(
                    int(row['declared_complete'] is True and row.get('passed') is False)
                    - int(control['declared_complete'] is True and control.get('passed') is False))
            for field, destination in [('total_cost_usd', cost_deltas), ('wall_seconds', time_deltas)]:
                if row.get(field) is not None and control.get(field) is not None:
                    destination[row['task_id']].append(row[field] - control[field])
            wins += delta > 0
            losses += delta < 0
            ties += delta == 0
        means = {task: statistics.mean(values) for task, values in sorted(task_deltas.items())}
        result['paired'] = {
            'wins': sum(v > 0 for v in means.values()),
            'losses': sum(v < 0 for v in means.values()),
            'ties': sum(v == 0 for v in means.values()),
            'trial_wins': wins, 'trial_losses': losses, 'trial_ties': ties,
            'missing_baseline_pairs': missing,
            'task_deltas': means,
            'mean_task_delta': statistics.mean(means.values()) if means else None,
            'descriptive_bootstrap_95_percent': cluster_interval(list(means.values())),
        }
        for metric, differences in [('false_completion', false_deltas), ('cost_usd', cost_deltas),
                                    ('wall_seconds', time_deltas)]:
            metric_means = {task: statistics.mean(values) for task, values in sorted(differences.items())}
            result['paired'][metric] = {
                'complete_pairs': sum(map(len, differences.values())),
                'task_deltas': metric_means,
                'mean_task_delta': statistics.mean(metric_means.values()) if metric_means else None,
                'descriptive_bootstrap_95_percent': cluster_interval(list(metric_means.values())),
            }
        output['arms'][arm] = result
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipts', type=Path)
    parser.add_argument('--baseline', default='original_cp_05')
    parser.add_argument('--schedule', type=Path, required=True, help='Frozen JSON array of expected trial identities')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    rendered = json.dumps(analyze(json.loads(args.receipts.read_text()), args.baseline,
        json.loads(args.schedule.read_text())), indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end='')


if __name__ == '__main__':
    main()
