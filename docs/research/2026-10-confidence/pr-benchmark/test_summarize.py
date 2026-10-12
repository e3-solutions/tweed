import unittest
from summarize import aggregate, analyze, cluster_interval


class PairedAnalysisTests(unittest.TestCase):
    def test_repetitions_do_not_create_task_clusters(self):
        rows = []
        for task, delta in [('a', 1), ('b', -1)]:
            for repeat in range(5):
                for arm in ['original_cp_05', 'candidate']:
                    passed = (arm == 'candidate') == (delta > 0)
                    rows.append(dict(task_id=task, arm_id=arm, repeat=repeat, passed=passed))
        result = analyze(rows)['arms']['candidate']['paired']
        self.assertEqual(result['task_deltas'], {'a': 1, 'b': -1})
        self.assertEqual(result['mean_task_delta'], 0)
        self.assertEqual(result['descriptive_bootstrap_95_percent'], [-1, 1])

    def test_missing_measurements_are_not_zero_or_false_claims(self):
        result = aggregate([{'passed': False, 'harness_invalid': True},
                            {'passed': False, 'declared_complete': True, 'total_cost_usd': 2}])
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(result['harness_invalid'], 1)
        self.assertEqual(result['false_completion'], 1)
        self.assertEqual(result['completion_unknown'], 1)
        self.assertEqual(result['cost_unknown'], 1)
        self.assertEqual(result['mean_known_cost_usd'], 2)

    def test_duplicate_identities_fail_instead_of_double_counting(self):
        row = dict(task_id='a', arm_id='original_cp_05', repeat=1, passed=True)
        with self.assertRaisesRegex(ValueError, 'Duplicate trial'):
            analyze([row, row])

    def test_zero_difference_interval_is_zero(self):
        self.assertEqual(cluster_interval([0, 0, 0]), [0, 0])

    def test_ungraded_completion_is_unknown_and_invalid_success_not_verified(self):
        result = aggregate([dict(passed=None, declared_complete=True),
                            dict(passed=True, harness_invalid=True)])
        self.assertEqual(result['false_completion'], 0)
        self.assertEqual(result['grading_unknown'], 1)
        self.assertEqual(result['passed'], 0)
        self.assertEqual(result['oracle_passed_including_invalid'], 1)

    def test_missing_repeat_remains_in_frozen_denominator(self):
        expected = [dict(task_id='a', arm_id=arm, repeat=repeat)
                    for arm in ['original_cp_05', 'candidate'] for repeat in [1, 2]]
        rows = [dict(**expected[0], passed=True), dict(**expected[1], passed=True),
                dict(**expected[2], passed=True)]
        result = analyze(rows, expected=expected)
        candidate = result['arms']['candidate']
        self.assertEqual(candidate['attempts'], 2)
        self.assertEqual(candidate['receipts_missing'], 1)
        self.assertEqual(candidate['success_rate'], 0.5)
        self.assertEqual(candidate['paired']['task_deltas'], {'a': -0.5})
        self.assertEqual(candidate['paired']['losses'], 1)

    def test_unregistered_receipt_is_rejected(self):
        row = dict(task_id='a', arm_id='original_cp_05', repeat=1, passed=True)
        with self.assertRaisesRegex(ValueError, 'outside frozen schedule'):
            analyze([row], expected=[])


if __name__ == '__main__':
    unittest.main()
