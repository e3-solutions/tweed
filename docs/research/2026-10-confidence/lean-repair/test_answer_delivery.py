"""Actual missed wordings plus adjacent questions that must not get this answer."""
import unittest
from answer_delivery import matches

DECISION = {
    'id': 'numeric-over-saved',
    'groups': [
        ['numeric', 'number', 'positive', 'explicit'],
        ['resume', 'saved', 'checkpoint'],
        ['override', 'precedence', 'priority', 'wins', 'takes'],
    ],
}


class AnswerDeliveryRegression(unittest.TestCase):
    def test_observed_baseline_question_receives_missing_answer(self):
        question = ('If an operator passes the budget option on resume, should '
                    'that CLI value replace the budget saved in the checkpoint, '
                    'including turning a disabled budget back on or turning an '
                    'enabled one off? Or should a resumed run always keep the saved budget?')
        self.assertTrue(matches(question, DECISION))

    def test_observed_revised_question_receives_missing_answer(self):
        question = ('On resume, if the CLI gives a different budget from an explicit '
                    'choice saved in the checkpoint, should the CLI value (A) win '
                    'quietly, (B) win with a warning, (C) lose to the checkpoint, or '
                    '(D) cause the run to refuse to resume? This also covers turning '
                    'the budget off or back on from the CLI.')
        self.assertTrue(matches(question, DECISION))

    def test_adjacent_questions_do_not_receive_numeric_precedence_answer(self):
        for question in (
            'Should the environment override the saved checkpoint budget?',
            'Should startup and resume show the budget from the CLI or checkpoint?',
            'Should an invalid CLI value fail before resuming the saved checkpoint?',
            'On a fresh run without saved state, should the CLI value replace the environment?',
        ):
            with self.subTest(question=question):
                self.assertFalse(matches(question, DECISION))


if __name__ == '__main__':
    unittest.main()
