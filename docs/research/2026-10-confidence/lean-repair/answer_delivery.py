"""Narrow lexical compatibility correction; never a semantic intake grader.

Old frozen interviews are unchanged. New consumers may use these additional
wordings when delivering scripted answers. Matching means an answer is delivered,
not that the question is sufficient or that the user has settled other choices.
The fresh repair cohort is fully specified and does not use this simulator.
"""

ALIASES = {
    'numeric': ('cli value', 'cli gives', 'cli option', 'budget option',
                'operator passes', 'command-line value'),
    'override': ('replace', 'win quietly', 'win with', 'lose to', 'turn it back on'),
}


def matches(question, decision):
    value = question.casefold()
    if decision.get('id') == 'numeric-over-saved' and not any(
            context in value for context in ('resume', 'checkpoint', 'saved budget')):
        return False
    return all(
        any(token in value for word in group
            for token in (word, *ALIASES.get(word, ())))
        for group in decision['groups']
    )
