"""The methodology document and the tool that serves it.

The point of these tests is that a documentation tool fails quietly. If a topic
stops resolving, the agent does not crash — it says the docs don't cover the
question, which reads exactly like a correct answer. So the agreement between
the slugs and the document's headings is asserted in both directions, and the
tool's three paths are exercised against the real file.
"""
import pytest

import methodology


class TestTheTopicMap:
    def test_every_slug_points_at_a_real_heading(self):
        """A renamed heading must fail here, not go silently unanswerable."""
        present = methodology.sections()
        missing = {slug: h for slug, h in methodology.TOPICS.items() if h not in present}
        assert not missing, f"topics point at headings that no longer exist: {missing}"

    def test_every_heading_has_a_slug(self):
        """A new section nobody can ask for is a section nobody will read."""
        mapped = set(methodology.TOPICS.values())
        unmapped = [h for h in methodology.sections() if h not in mapped]
        assert not unmapped, f"document sections with no topic slug: {unmapped}"

    def test_all_topics_are_available(self):
        assert set(methodology.available()) == set(methodology.TOPICS)


class TestParsing:
    def test_sections_carry_real_prose(self):
        for heading, body in methodology.sections().items():
            assert len(body) > 100, f"section {heading!r} looks truncated"
            assert not body.startswith("#"), f"section {heading!r} swallowed a heading"

    def test_lookup_returns_the_named_section(self):
        heading, body = methodology.lookup("ol_grades")
        assert heading == "What the O-line grades do and do not measure"
        assert "Individual blockers are not" in body

    def test_lookup_is_case_and_space_insensitive(self):
        assert methodology.lookup("  EPA  ") == methodology.lookup("epa")

    def test_lookup_rejects_an_invented_slug(self):
        assert methodology.lookup("how are grades made") is None

    def test_a_missing_document_is_survivable(self, monkeypatch):
        """The container copies api/ wholesale, but a tool must not 500 on IO."""
        monkeypatch.setattr(methodology, "DOC_PATH", "does-not-exist.md")
        monkeypatch.setattr(methodology, "sections", lambda _c={}: {})
        assert methodology.available() == []
        assert methodology.lookup("epa") is None


@pytest.fixture
def tool():
    import llm

    ctx = llm._Ctx()
    return {t.name: t.func for t in llm._build_tools(ctx)}["get_methodology"]


class TestTheTool:
    def test_it_is_registered(self):
        import llm

        names = {t.name for t in llm._build_tools(llm._Ctx())}
        assert "get_methodology" in names

    def test_no_topic_lists_what_is_documented(self, tool):
        out = tool()
        assert "Documented topics:" in out
        for slug in methodology.TOPICS:
            assert slug in out

    def test_a_topic_returns_that_section_with_its_citation(self, tool):
        out = tool("power_rankings")
        assert out.startswith("[METHODOLOGY.md — How the power rankings are computed]")
        assert "off_epa_sum" in out

    def test_an_invented_topic_hands_back_the_real_list(self, tool):
        """Never guess which section was meant: a confidently quoted wrong
        passage is worse than spending another turn."""
        out = tool("how the grades work")
        assert "No documented topic" in out
        assert "Documented topics:" in out

    def test_every_slug_reaches_its_section_through_the_tool(self, tool):
        for slug, heading in methodology.TOPICS.items():
            out = tool(slug)
            assert out.startswith(f"[METHODOLOGY.md — {heading}]"), slug


class TestTheSystemPrompt:
    """Routing is driven by the prompt, so the vocabulary has to be in it."""

    def test_the_tool_and_its_topics_are_advertised(self):
        import llm

        line = next(l for l in llm.SYSTEM_PROMPT.splitlines()
                    if l.startswith("- get_methodology"))
        for slug in methodology.TOPICS:
            assert slug in line, f"{slug} is not offered in the system prompt"

    def test_the_prompt_forbids_answering_methodology_from_memory(self):
        import llm

        assert "never from memory" in llm.SYSTEM_PROMPT


class TestTheGoldSet:
    """Free checks on the billed eval's expectations.

    The ask eval is opt-in because it spends real tokens, so a typo in a gold
    case would sit undiscovered until someone paid to find it — and would look
    like a routing regression rather than a bad expectation.
    """

    @staticmethod
    def _gold():
        # Loaded by path, not by name: tests/ is a package and the eval module
        # is not importable as a bare name from inside another test.
        import importlib.util
        import os

        path = os.path.join(os.path.dirname(__file__), "test_ask_eval.py")
        spec = importlib.util.spec_from_file_location("_gold_set", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_expected_topic_exists(self):
        bad = [
            (g["q"], g["args"].get("topic"))
            for g in self._gold().GOLD
            if g.get("tool") == "get_methodology"
            and g["args"].get("topic") not in methodology.TOPICS
        ]
        assert not bad, f"gold cases expect topics that don't exist: {bad}"

    def test_every_topic_has_a_question(self):
        """A section nothing asks for is a section that can break unnoticed."""
        asked = {
            g["args"].get("topic")
            for g in self._gold().GOLD
            if g.get("tool") == "get_methodology"
        }
        unasked = set(methodology.TOPICS) - asked
        assert not unasked, f"documented topics with no gold question: {unasked}"

    def test_every_methodology_case_is_tagged(self):
        """The capability report card groups by tag, so an untagged case is a
        case whose category silently reads as zero."""
        untagged = [
            g["q"] for g in self._gold().GOLD
            if g.get("tool") == "get_methodology"
            and "methodology" not in g.get("tags", [])
        ]
        assert not untagged, f"methodology cases missing their tag: {untagged}"
