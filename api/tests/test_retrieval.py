"""Offline tests for documentation retrieval.

Everything here except the final integration test runs with no API key, no
network, and no model download — that is the point of the `Embedder` seam. The
chunking tests are pure text; the ranking tests inject a deterministic stub
embedder, so a "similarity" ranking is exactly reproducible.
"""
import os

import numpy as np
import pytest

import retrieval
from retrieval import Chunk, Index, load_chunks, split_markdown


# ── Chunking: pure text, no model ─────────────────────────────────────────────

SAMPLE = """# Doc Title

Intro paragraph before any section.

## First Section

Body of the first section.

### Nested Detail

Detail body.

## Second Section

Body of the second section.
"""


def test_headings_become_chunk_boundaries():
    chunks = split_markdown(SAMPLE, "sample.md")
    headings = [c.heading for c in chunks]
    assert headings == [
        "Doc Title",
        "Doc Title > First Section",
        "Doc Title > First Section > Nested Detail",
        "Doc Title > Second Section",
    ]


def test_chunks_carry_source_and_heading_path():
    chunks = split_markdown(SAMPLE, "sample.md")
    nested = next(c for c in chunks if c.heading.endswith("Nested Detail"))
    assert nested.source == "sample.md"
    assert nested.citation == "sample.md > Doc Title > First Section > Nested Detail"
    assert nested.text == "Detail body."


def test_nesting_pops_back_to_shallower_level():
    """A `##` after a `###` replaces the deeper level rather than nesting under it."""
    chunks = split_markdown(SAMPLE, "sample.md")
    second = chunks[-1]
    assert second.heading == "Doc Title > Second Section"


def test_content_before_first_heading_is_kept():
    chunks = split_markdown("Preamble text.\n\n## Section\n\nBody.\n", "x.md")
    assert chunks[0].heading == ""
    assert chunks[0].text == "Preamble text."
    assert chunks[0].citation == "x.md"


def test_hash_inside_fenced_code_is_not_a_heading():
    text = "## Real Heading\n\n```bash\n# not a heading\necho hi\n```\n\nAfter.\n"
    chunks = split_markdown(text, "x.md")
    assert [c.heading for c in chunks] == ["Real Heading"]
    assert "# not a heading" in chunks[0].text


def test_empty_sections_are_dropped():
    chunks = split_markdown("## Empty\n\n## Full\n\nBody.\n", "x.md")
    assert [c.heading for c in chunks] == ["Full"]


def test_long_sections_split_on_paragraph_boundaries():
    para = "word " * 60          # ~300 chars
    body = "\n\n".join([para.strip()] * 8)   # ~2400 chars, over the cap
    chunks = split_markdown(f"## Big\n\n{body}\n", "x.md")
    assert len(chunks) > 1
    assert all(c.heading == "Big" for c in chunks)
    assert all(len(c.text) <= retrieval._MAX_CHUNK_CHARS + 400 for c in chunks)
    # No text is lost in the split.
    assert sum(c.text.count("word") for c in chunks) == 480


def test_missing_corpus_files_are_skipped_not_fatal():
    assert load_chunks(["/nonexistent/nope.md"]) == []


def test_real_corpus_loads_and_has_provenance():
    chunks = load_chunks()
    assert chunks, "the shipped corpus should not be empty"
    assert all(c.source and c.text for c in chunks)
    assert any(c.source == "METHODOLOGY.md" for c in chunks)


def test_fingerprint_changes_with_content():
    a = [Chunk("f.md", "H", "body one")]
    b = [Chunk("f.md", "H", "body two")]
    assert retrieval.corpus_fingerprint(a) != retrieval.corpus_fingerprint(b)
    assert retrieval.corpus_fingerprint(a) == retrieval.corpus_fingerprint(list(a))


# ── Ranking: deterministic stub through the Embedder seam ─────────────────────

class StubEmbedder:
    """Bag-of-words vectors over a fixed vocabulary.

    Deterministic, offline, and dependency-free, but a real vector space: cosine
    similarity behaves the way it does for the actual model, so ranking
    assertions here are meaningful rather than tautological.
    """

    VOCAB = ["power", "rankings", "epa", "shrinkage", "splits",
             "pressure", "reconcile", "official", "kicker", "grade"]

    def __init__(self):
        self.calls = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        out = np.zeros((len(texts), len(self.VOCAB)), dtype=np.float32)
        for row, text in enumerate(texts):
            words = text.lower().split()
            for col, term in enumerate(self.VOCAB):
                out[row, col] = sum(term in word for word in words)
        return out


@pytest.fixture
def stub_index():
    chunks = [
        Chunk("METHODOLOGY.md", "How the power rankings are computed",
              "power rankings use net epa per play with shrinkage"),
        Chunk("METHODOLOGY.md", "How situational splits are built",
              "splits are long format and single dimension by pressure"),
        Chunk("METHODOLOGY.md", "How the platform reconciles",
              "splits reconcile exactly with official weekly totals"),
    ]
    return Index(chunks, StubEmbedder())


def test_search_ranks_the_matching_chunk_first(stub_index):
    hits = stub_index.search("how are power rankings computed", k=3)
    assert hits[0].heading == "How the power rankings are computed"


def test_search_returns_provenance_and_score(stub_index):
    hit = stub_index.search("power rankings shrinkage", k=1)[0]
    assert hit.source == "METHODOLOGY.md"
    assert hit.citation.startswith("METHODOLOGY.md > ")
    assert 0.0 < hit.score <= 1.0


def test_search_distinguishes_between_topics(stub_index):
    assert stub_index.search("reconcile official totals", k=1)[0].heading == (
        "How the platform reconciles")
    assert stub_index.search("pressure splits", k=1)[0].heading == (
        "How situational splits are built")


def test_search_respects_k(stub_index):
    assert len(stub_index.search("splits epa rankings", k=2)) <= 2


def test_scores_are_descending(stub_index):
    hits = stub_index.search("splits epa rankings official", k=3)
    assert hits == sorted(hits, key=lambda c: -c.score)


def test_offtopic_query_returns_no_results(stub_index):
    """A query sharing no vocabulary scores 0 and is filtered by MIN_SCORE."""
    assert stub_index.search("who won the super bowl", k=3) == []


def test_blank_query_returns_no_results(stub_index):
    assert stub_index.search("   ", k=3) == []


def test_empty_corpus_searches_cleanly():
    empty = Index([], StubEmbedder())
    assert empty.search("anything", k=3) == []


def test_vectors_are_l2_normalized(stub_index):
    norms = np.linalg.norm(stub_index.vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


# ── Caching ───────────────────────────────────────────────────────────────────

def test_cache_round_trips_and_skips_re_embedding(tmp_path):
    chunks = [Chunk("f.md", "H", "power rankings epa")]
    cache = str(tmp_path / "idx.npz")

    first = Index(chunks, StubEmbedder(), cache_path=cache)
    assert first.embedder.calls == 1
    assert os.path.exists(cache)

    second = Index(chunks, StubEmbedder(), cache_path=cache)
    assert second.embedder.calls == 0, "cached vectors should be reused"
    assert np.allclose(first.vectors, second.vectors)


def test_cache_is_invalidated_when_docs_change(tmp_path):
    cache = str(tmp_path / "idx.npz")
    Index([Chunk("f.md", "H", "original text")], StubEmbedder(), cache_path=cache)

    changed = Index([Chunk("f.md", "H", "edited text")], StubEmbedder(),
                    cache_path=cache)
    assert changed.embedder.calls == 1, "edited docs must be re-embedded"


def test_corrupt_cache_falls_back_to_embedding(tmp_path):
    cache = tmp_path / "idx.npz"
    cache.write_bytes(b"not a real npz file")
    index = Index([Chunk("f.md", "H", "text")], StubEmbedder(), cache_path=str(cache))
    assert index.embedder.calls == 1
    assert index.vectors.shape[0] == 1


# ── The lazy-load contract ────────────────────────────────────────────────────

def test_importing_retrieval_does_not_load_the_model():
    """Importing this module must not import sentence_transformers or torch —
    API startup and the offline suite cannot pay an 80MB model load."""
    import sys

    assert "sentence_transformers" not in sys.modules
    assert "torch" not in sys.modules


def test_local_embedder_construction_does_not_load_the_model():
    embedder = retrieval.LocalEmbedder()
    assert embedder._model is None


# ── Optional integration check with the real model ────────────────────────────

@pytest.mark.skipif(
    not os.environ.get("RUN_RETRIEVAL_INTEGRATION"),
    reason="downloads an ~80MB model — set RUN_RETRIEVAL_INTEGRATION=1 to run",
)
def test_real_model_retrieves_power_rankings_methodology():
    pytest.importorskip("sentence_transformers")
    hits = retrieval.search("how are the power rankings calculated", k=3)
    assert hits, "real corpus should answer a methodology question"
    joined = " ".join(h.text.lower() for h in hits)
    assert "epa" in joined
    assert any("power rankings" in h.heading.lower() for h in hits)
