"""Exact code revisions reviewed as equivalent to an existing validation policy.

The fingerprint includes preparation orchestration. Deferring its duplicate
validation to the existing locked release validator preserves the statistical
checks. This alias keeps existing releases readable for that exact code tree.
Any further fingerprinted code change produces its own revision automatically.
"""


EQUIVALENT_REVISIONS = {
    '107fc06fd1fe6b117a05d286951ef99824b5f4fb62ad3157c13f1c714229b372':
        'f72611443cf21bba4fc9ecec485459304b10e6094c4997339747b4ac16ef7ef4',
}


def compatible_revision(code_revision):
    return EQUIVALENT_REVISIONS.get(code_revision, code_revision)
