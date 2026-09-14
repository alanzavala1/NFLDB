"""Free checks for the answer graders shared by both eval arms.

Two directions, both required: each grader must ACCEPT the phrasings a correct
answer actually takes, and must REJECT wrong-but-plausible answers. The reject
direction is what keeps the headline accuracy number honest — a grader that
cannot fail is not a grader.
"""
import pytest

from tests.test_ask_eval import (
    award_polarity_in,
    declines_offtopic,
    down_in,
    name_in,
    num_in,
    pct_in,
    record_in,
    text_in,
)


# ── record_in ─────────────────────────────────────────────────────────────────

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


# ── num_in ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "answer,value",
    [
        ("He threw 15 interceptions.", 15),
        ("He had 1,234 rushing yards in 2020.", 1234),
        ("Ranked 3 in the league.", 3),
        ("The answer is 3.", 3),          # sentence-final period is not a decimal
        ("He scored 15 touchdowns", 15.0),
        ("He had 27.0 tackles.", 27),     # models echo stored floats verbatim
    ],
)
def test_num_grader_accepts_standalone_numbers(answer, value):
    assert num_in(answer, value)


@pytest.mark.parametrize(
    "answer,value",
    [
        ("In 2023 he was excellent.", 3),      # 3 inside the season year
        ("In 2023 he was excellent.", 202),    # prefix of the year
        ("He gained 150 yards.", 15),          # prefix of a larger number
        ("He averaged 4.3 per carry.", 3),     # decimal tail
        ("He averaged 15.2 yards.", 15),       # decimal head
        ("He threw 14 interceptions.", 15),    # plainly different number
    ],
)
def test_num_grader_rejects_embedded_or_wrong_numbers(answer, value):
    assert not num_in(answer, value)


# ── pct_in ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "answer,value",
    [
        ("Success rate of 44.9% in the red zone.", 44.9),
        ("They succeeded about 45% of the time.", 44.9),
        ("A 62.0% success rate.", 62.04),
    ],
)
def test_pct_grader_accepts_rounded_forms(answer, value):
    assert pct_in(answer, value)


@pytest.mark.parametrize(
    "answer,value",
    [
        ("Success rate of 44.9%.", 4.9),   # embedded inside the real figure
        ("Success rate of 34.9%.", 44.9),  # plainly different figure
        ("They ran 449 plays.", 44.9),     # digits of the target, no percentage
    ],
)
def test_pct_grader_rejects_embedded_or_wrong_percentages(answer, value):
    assert not pct_in(answer, value)


# ── award_polarity_in ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "answer",
    [
        "Yes — he won MVP in 2024.",
        "He won the MVP award for the 2024 season.",
        "Yes, once.",
    ],
)
def test_award_grader_accepts_affirmations_when_player_won(answer):
    assert award_polarity_in(answer, [2024])


@pytest.mark.parametrize(
    "answer",
    [
        "No, he has never won MVP.",           # the both-ways hole this replaced
        "He has not won an MVP award.",
        "He was in the MVP conversation but came up short.",
    ],
)
def test_award_grader_rejects_denials_when_player_won(answer):
    assert not award_polarity_in(answer, [2024])


def test_award_grader_requires_denial_when_player_never_won():
    assert award_polarity_in("No, he has never won MVP.", [])
    assert not award_polarity_in("Yes, he won MVP in 2019.", [])


# ── declines_offtopic ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "answer",
    [
        "I can't help with restaurants — I only answer questions about NFL stats.",
        "That's outside what I cover; I'm a football statistics assistant and cannot recommend pizza places.",
    ],
)
def test_offtopic_grader_accepts_scoped_refusals(answer):
    assert declines_offtopic(answer)


@pytest.mark.parametrize(
    "answer",
    [
        "Sure! Tony's Pizza on 5th is great.",                    # complied
        "Sorry, I'm not sure about pizza places.",                # no scope statement
        "Great question! The NFL has many stadiums with pizza.",  # on-topic words, no refusal
    ],
)
def test_offtopic_grader_rejects_compliance_and_unscoped_apologies(answer):
    assert not declines_offtopic(answer)


# ── name_in / text_in / down_in sanity ────────────────────────────────────────

def test_name_grader_matches_surname_across_abbreviated_forms():
    assert name_in("Nick Bosa led the league.", ["N.Bosa"])
    assert not name_in("Myles Garrett led the league.", ["N.Bosa"])


def test_text_grader_is_case_insensitive_and_rejects_absent_options():
    assert text_in("The Chiefs won it all.", ["chiefs"])
    assert not text_in("The Chiefs won it all.", ["eagles", "bills"])


def test_down_grader_accepts_both_ordinal_forms_and_rejects_others():
    assert down_in("They ran most on first down.", 1)
    assert down_in("Mostly on 3rd down.", 3)
    assert not down_in("They ran most on first down.", 3)


# ── provenance audit ─────────────────────────────────────────────────────────

def test_provenance_audit_passes_sourced_figures_and_flags_unsourced_ones():
    from tests.test_ask_eval import _unsupported_figures

    raw = ['{"att":303,"yards":1876,"success_pct":47.2}']
    sourced = "He threw for 1,876 yards on 303 attempts (47.2% success) in 2022, ranking 3rd."
    assert _unsupported_figures(sourced, raw) == []
    unsourced = "He threw for 2,340 yards on 303 attempts in 2022."
    assert _unsupported_figures(unsourced, raw) == ["2340"]


def test_provenance_audit_matches_numerically_across_serialization_formats():
    from tests.test_ask_eval import _unsupported_figures

    raw = ['{"tackles":36.0,"pct":0.824,"success_rate":0.444,"yards":515.0}']
    answer = ("He made 36 tackles; the team's .824 win pct (82.4%) and 44.4% "
              "success rate led the 49ers to 515 total yards.")
    assert _unsupported_figures(answer, raw) == []


def test_provenance_audit_whitelists_years_ranks_and_small_ordinals():
    from tests.test_ask_eval import _unsupported_figures

    answer = "In 2023 he ranked 2nd on 1st downs; the data covers 1999 through 2026."
    assert _unsupported_figures(answer, ["{}"]) == []


# ── gold-set hygiene (free: the module import costs nothing) ─────────────────

_ALLOWED_TAGS = {
    "lookup", "splits-off", "splits-def", "games", "career", "teams",
    "leaders", "rankings", "era", "ambiguity", "phrasing", "followup",
    "coverage-honesty", "plays",
    # Questions about how the platform itself computes things, answered from
    # METHODOLOGY.md via get_methodology rather than from the database.
    "methodology",
}


def test_every_gold_case_is_tagged_from_the_known_taxonomy():
    from tests.test_ask_eval import GOLD

    for case in GOLD:
        assert case.get("tags"), f"untagged case: {case['q']}"
        unknown = set(case["tags"]) - _ALLOWED_TAGS
        assert not unknown, f"unknown tags {unknown}: {case['q']}"


def test_gold_questions_are_unique_and_key_categories_are_covered():
    from tests.test_ask_eval import GOLD

    questions = [case["q"] for case in GOLD]
    assert len(questions) == len(set(questions))
    tags = {tag for case in GOLD for tag in case["tags"]}
    for required in ("splits-def", "era", "ambiguity", "phrasing",
                     "coverage-honesty", "followup"):
        assert required in tags, f"no cases tagged {required}"
