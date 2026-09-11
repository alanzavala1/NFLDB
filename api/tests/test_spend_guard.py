"""The daily ceiling on the billed endpoint.

The per-IP limiter these sit beside is not a cost control — it is per key, so
rotating IPs walks around it. These tests are about the thing that actually
bounds the bill.
"""
import time

import pytest

from spend_guard import SpendGuard


class TestRequestCeiling:
    def test_allows_until_the_ceiling_then_refuses(self):
        g = SpendGuard(max_requests=3, max_tokens=10_000_000)
        for _ in range(3):
            assert g.exceeded() is None
            g.record_request()
        assert "request ceiling" in (g.exceeded() or "")

    def test_a_refused_request_is_not_counted(self):
        # A rejected call costs nothing, so it must not consume budget —
        # otherwise a blocked abuser keeps the endpoint shut indefinitely.
        g = SpendGuard(max_requests=1, max_tokens=10_000_000)
        g.record_request()
        assert g.exceeded() is not None
        assert g.exceeded() is not None            # still exactly at the ceiling
        assert g.snapshot()["requests"] == 1

    def test_the_window_rolls(self):
        g = SpendGuard(max_requests=1, max_tokens=10_000_000, window=0.05)
        g.record_request()
        assert g.exceeded() is not None
        time.sleep(0.06)
        assert g.exceeded() is None


class TestTokenCeiling:
    def test_trips_on_tokens_even_with_requests_to_spare(self):
        g = SpendGuard(max_requests=1000, max_tokens=100)
        g.record_tokens({"uncached_input": 60, "output": 50})
        assert "token ceiling" in (g.exceeded() or "")

    def test_accepts_the_usage_dict_llm_builds(self):
        g = SpendGuard(max_requests=1000, max_tokens=1000)
        g.record_tokens({
            "uncached_input": 10, "cache_creation_input": 20,
            "cache_read_input": 30, "output": 40,
        })
        assert g.snapshot()["tokens"] == 100

    def test_accepts_a_plain_total(self):
        g = SpendGuard(max_requests=1000, max_tokens=1000)
        g.record_tokens(500)
        assert g.snapshot()["tokens"] == 500


class TestNeverBreaksARequest:
    """Recording is bookkeeping for a question that already succeeded. It must
    not be able to raise — a billing counter failing a served answer would be a
    worse outcome than the accounting being slightly wrong."""

    @pytest.mark.parametrize("bad", [None, {}, "nonsense", {"x": None}, {"x": object()}])
    def test_garbage_usage_is_ignored_not_raised(self, bad):
        g = SpendGuard(max_requests=10, max_tokens=10)
        g.record_tokens(bad)
        assert g.exceeded() is None

    def test_zero_and_negative_totals_do_not_accumulate(self):
        g = SpendGuard(max_requests=10, max_tokens=10)
        g.record_tokens(0)
        g.record_tokens(-5)
        assert g.snapshot()["tokens"] == 0


class TestRequestCeilingCoversPathsThatReportNoTokens:
    def test_a_path_that_never_reports_tokens_is_still_bounded(self):
        # The streaming endpoint tracked no usage at all before this change.
        # The request ceiling is what makes the guarantee hold regardless.
        g = SpendGuard(max_requests=2, max_tokens=10_000_000)
        for _ in range(2):
            g.record_request()          # deliberately never record_tokens
        assert g.exceeded() is not None
