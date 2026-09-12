"""The platform's own documentation, addressable by topic.

`METHODOLOGY.md` explains how this platform computes what it reports. The agent
is forbidden from answering from memory, so without a tool it could say what a
number *is* but not how it was produced — and "I can't explain my own grades"
is a poor answer from a platform whose entire argument is that its definitions
are verified.

**Why a topic map and not retrieval.** This started as embeddings: chunk the
document, embed with MiniLM, rank by cosine. That works, and it was measured
working. It was also 338 lines of machinery and 183MB of torch over a 161-line
document whose author had already solved the retrieval problem by writing
headings. Worse, similarity search can return the wrong passage and there is no
way to know: with the README in the corpus, the correct section reached the top
three for only 8 of 11 methodology questions, because summary prose *about* a
topic outranks the section that actually explains it.

Selecting a section by name cannot do that. It is exact, it is deterministic, it
has no model to download on a cold start and no vector cache to invalidate, and
it fails loudly rather than plausibly. It is also the same argument the agent
itself is built on: a closed vocabulary the server owns beats free-form matching
the model has to get right.

The slugs live here rather than being derived from the headings, so that editing
a heading cannot silently repoint a topic at nothing. `test_methodology.py`
asserts the two stay in agreement in both directions.
"""
from __future__ import annotations

import os
import re

DOC_PATH = os.path.join(os.path.dirname(__file__), "docs", "METHODOLOGY.md")

# topic slug -> the exact `##` heading it addresses.
TOPICS: dict[str, str] = {
    "power_rankings":   "How the power rankings are computed",
    "player_grades":    "How player game grades are computed",
    "reconciliation":   "How the platform reconciles with official NFL stats",
    "epa":              "What EPA means on this platform",
    "splits":           "How situational splits are built",
    "coverage_limits":  "Why some data is missing for older seasons",
    "ol_grades":        "What the O-line grades do and do not measure",
    "agent_evaluation": "How the question-answering agent is evaluated",
    "typed_tools":      "Why the agent uses typed tools instead of writing SQL",
}


def _read_doc() -> str:
    """The raw document, or empty string if it isn't there.

    A missing file must not 500 the ask endpoint. The tool turns an empty
    document into "the docs don't cover this", which is the same answer the
    agent gives for anything it cannot retrieve.
    """
    try:
        with open(DOC_PATH, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def sections(_cache: dict[str, dict[str, str]] = {}) -> dict[str, str]:
    """`{heading: body}` for every `##` section, parsed once per process.

    Bodies keep their own markdown — tables and indented formulas are part of
    the explanation, and the model quotes them back accurately.
    """
    if "v" in _cache:
        return _cache["v"]
    out: dict[str, str] = {}
    heading, body = None, []
    for line in _read_doc().splitlines():
        m = re.match(r"^##\s+(.*\S)\s*$", line)
        if m:
            if heading:
                out[heading] = "\n".join(body).strip()
            heading, body = m.group(1), []
        elif heading:
            body.append(line)
    if heading:
        out[heading] = "\n".join(body).strip()
    _cache["v"] = out
    return out


def available() -> list[str]:
    """Topic slugs whose section is actually present in the document."""
    present = sections()
    return [slug for slug, heading in TOPICS.items() if heading in present]


def lookup(topic: str) -> tuple[str, str] | None:
    """`(heading, body)` for a topic slug, or None if it isn't one.

    Matching is exact on the slug. Near-misses are deliberately not resolved —
    the valid slugs are listed in the tool's own description and in the system
    prompt, so a miss means the model invented one, and answering a question it
    didn't ask is how a wrong passage gets quoted confidently.
    """
    heading = TOPICS.get(topic.strip().lower())
    if heading is None:
        return None
    body = sections().get(heading)
    return (heading, body) if body else None
