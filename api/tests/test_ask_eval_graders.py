"""Free checks for answer-grader equivalence rules shared by both eval arms."""
import pytest

from tests.test_ask_eval import record_in


@pytest.mark.parametrize(
    "answer",
    [
        "They finished 14-3.",
        "They finished with 14 wins, 3 losses.",
        "The record was 14 wins and 3 losses.",
        "They won 14 games and lost 3.",
    ],
)
def test_record_grader_accepts_equivalent_phrasings(answer):
    assert record_in(answer, "14-3")


@pytest.mark.parametrize(
    "answer",
    [
        "They finished 14-4.",
        "They had 14 wins and 4 losses.",
        "They won 13 games and lost 3.",
    ],
)
def test_record_grader_rejects_different_records(answer):
    assert not record_in(answer, "14-3")
