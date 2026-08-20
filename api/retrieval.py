"""Dense retrieval over this project's own documentation.

Why this exists: the /ask agent can report what the numbers are, because every
figure routes through a typed tool over verified data. It could not explain
*how* those numbers are produced — "how are the power rankings computed" had no
tool behind it, and the system prompt forbids answering from memory. This module
is the retrieval half of that missing tool.

Two design constraints shape the code:

1. **The corpus layer has no model dependency.** Loading and chunking markdown is
   pure text work, so those tests run offline with nothing installed beyond the
   standard library and numpy.
2. **The embedder is a seam, not a hard-wired model.** `Embedder` is a protocol;
   `LocalEmbedder` is one implementation that wraps sentence-transformers and
   loads its weights lazily on first `encode`, never at import. That keeps API
   startup and unrelated tests free of an 80MB model load, lets tests inject a
   deterministic stub, and leaves room to swap in a hosted embedding API later
   without touching the tool or the prompt.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

import numpy as np

_API_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_DIR = os.path.dirname(_API_DIR)

# The indexed corpus, in priority order.
#
# api/docs/ is the corpus that actually ships: the Dockerfile copies `api/`, so
# anything here reaches the deployed container. The repo-root README is indexed
# too when present (local dev and the repo), but it is NOT copied into the
# image, so METHODOLOGY.md is written to stand on its own. Missing files are
# skipped rather than raising — a partial corpus is the normal deployed state.
#
# Deliberately excluded: notes/ is gitignored and .dockerignore'd because it
# holds personal working notes, and it is a pre-build brief that no longer
# matches the code. /ask is a public endpoint that returns retrieved text
# verbatim, so only reviewed, current, publishable docs belong here.
CORPUS_PATHS: tuple[str, ...] = (
    os.path.join(_API_DIR, "docs", "METHODOLOGY.md"),
    os.path.join(_REPO_DIR, "README.md"),
)

# MiniLM truncates at 256 word pieces, so oversized sections are split on
# paragraph boundaries before embedding rather than silently losing their tails.
_MAX_CHUNK_CHARS = 1200

# Below this cosine similarity a "match" is noise. Returning nothing is the
# correct answer for an off-topic query, and the tool says so explicitly.
MIN_SCORE = 0.15

_MODEL_NAME = "all-MiniLM-L6-v2"
_CACHE_PATH = os.path.join(_API_DIR, "data", "doc_index.npz")


@dataclass
class Chunk:
    """One retrievable passage plus the provenance needed to attribute it."""

    source: str          # filename only, e.g. "METHODOLOGY.md"
    heading: str         # heading path, e.g. "NFLDB Methodology > How EPA works"
    text: str
    score: float = field(default=0.0, compare=False)

    @property
    def citation(self) -> str:
        return f"{self.source} > {self.heading}" if self.heading else self.source

    def embed_text(self) -> str:
        """What actually gets embedded. The heading path is prepended so a
        section's topic contributes to its vector — bodies often never repeat
        the words in their own heading ("power rankings" appears once, in the
        title of the section explaining them)."""
        return f"{self.heading}\n\n{self.text}" if self.heading else self.text


# ── Chunking (no model, no network) ───────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def split_markdown(text: str, source: str) -> list[Chunk]:
    """Split one markdown document into chunks on heading boundaries.

    Each heading starts a new chunk and carries the full heading path above it,
    so a retrieved passage can be attributed to file and section. Fenced code
    blocks are passed through untouched — a `#` comment inside a fence is not a
    heading. Sections longer than _MAX_CHUNK_CHARS are split again on blank
    lines. Content before the first heading belongs to the document root.
    """
    chunks: list[Chunk] = []
    # (level, title) stack. Levels are tracked explicitly rather than using list
    # position, because a document may start at any level and skip levels — an
    # `##` following a `###` must pop the deeper heading, not nest beneath it.
    path: list[tuple[int, str]] = []
    body: list[str] = []
    heading = ""
    in_fence = False

    def flush() -> None:
        content = "\n".join(body).strip()
        body.clear()
        if not content:
            return
        for part in _split_long(content):
            chunks.append(Chunk(source=source, heading=heading, text=part))

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            body.append(line)
            continue

        match = None if in_fence else _HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, title))
            heading = " > ".join(title for _, title in path)
        else:
            body.append(line)

    flush()
    return chunks


def _split_long(content: str) -> list[str]:
    """Split an over-long section on blank lines, packing paragraphs greedily."""
    if len(content) <= _MAX_CHUNK_CHARS:
        return [content]

    parts: list[str] = []
    current: list[str] = []
    size = 0
    for para in re.split(r"\n\s*\n", content):
        para = para.strip()
        if not para:
            continue
        if current and size + len(para) > _MAX_CHUNK_CHARS:
            parts.append("\n\n".join(current))
            current, size = [], 0
        current.append(para)
        size += len(para) + 2
    if current:
        parts.append("\n\n".join(current))
    return parts


def load_chunks(paths: Sequence[str] | None = None) -> list[Chunk]:
    """Load and chunk the corpus. Missing files are skipped, not fatal."""
    chunks: list[Chunk] = []
    for path in (CORPUS_PATHS if paths is None else paths):
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        chunks.extend(split_markdown(text, os.path.basename(path)))
    return chunks


def corpus_fingerprint(chunks: Sequence[Chunk]) -> str:
    """Hash of the corpus text, so cached vectors are reused only while the docs
    they were built from are unchanged."""
    digest = hashlib.sha256()
    digest.update(_MODEL_NAME.encode())
    for chunk in chunks:
        digest.update(chunk.source.encode())
        digest.update(chunk.heading.encode())
        digest.update(chunk.text.encode())
    return digest.hexdigest()


# ── Embedder seam ─────────────────────────────────────────────────────────────

@runtime_checkable
class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


class LocalEmbedder:
    """sentence-transformers all-MiniLM-L6-v2 (384-dim, ~80MB).

    The model is loaded on first `encode`, never at import: importing this
    module must stay cheap enough that API startup and the offline test suite
    never pay for it.
    """

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    print(f"[ask] loading embedding model: {self.model_name}")
                    self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._load().encode(texts), dtype=np.float32)


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """Row-normalize so cosine similarity is a single dot product."""
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


# ── Index ─────────────────────────────────────────────────────────────────────

class Index:
    """Chunks plus their L2-normalized vectors, searched by dot product.

    The embedder is injected, which is what makes the ranking tests
    deterministic and offline.
    """

    def __init__(self, chunks: Sequence[Chunk], embedder: Embedder,
                 cache_path: str | None = None) -> None:
        self.chunks = list(chunks)
        self.embedder = embedder
        self.cache_path = cache_path
        self.vectors = self._build()

    def _build(self) -> np.ndarray:
        if not self.chunks:
            return np.zeros((0, 0), dtype=np.float32)

        fingerprint = corpus_fingerprint(self.chunks)
        cached = self._read_cache(fingerprint)
        if cached is not None:
            return cached

        vectors = _l2_normalize(
            self.embedder.encode([c.embed_text() for c in self.chunks])
        )
        self._write_cache(fingerprint, vectors)
        return vectors

    def _read_cache(self, fingerprint: str) -> np.ndarray | None:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return None
        try:
            with np.load(self.cache_path, allow_pickle=False) as data:
                if str(data["fingerprint"]) != fingerprint:
                    return None
                vectors = data["vectors"]
            if vectors.shape[0] != len(self.chunks):
                return None
            return vectors.astype(np.float32)
        except Exception as error:
            print(f"[ask] ignoring unreadable doc index cache: {error}")
            return None

    def _write_cache(self, fingerprint: str, vectors: np.ndarray) -> None:
        if not self.cache_path:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            np.savez(self.cache_path, fingerprint=np.array(fingerprint),
                     vectors=vectors)
        except Exception as error:
            print(f"[ask] could not cache doc index: {error}")

    def search(self, query: str, k: int = 3,
               min_score: float = MIN_SCORE) -> list[Chunk]:
        """Top-k chunks above `min_score`, best first. Empty corpus or a blank
        query returns [] rather than raising."""
        query = (query or "").strip()
        if not query or not self.chunks or self.vectors.size == 0:
            return []

        scores = self.vectors @ _l2_normalize(self.embedder.encode([query]))[0]
        k = max(1, min(int(k), len(self.chunks)))
        top = np.argsort(-scores)[:k]

        hits: list[Chunk] = []
        for position in top:
            score = float(scores[position])
            if score < min_score:
                continue
            source = self.chunks[position]
            hits.append(Chunk(source=source.source, heading=source.heading,
                              text=source.text, score=round(score, 4)))
        return hits


# ── Module-level default index ────────────────────────────────────────────────

_default: Index | None = None
_default_lock = threading.Lock()


def get_index() -> Index:
    """The process-wide index over CORPUS_PATHS, built on first use.

    Building it triggers the model load, so this is called from the tool, never
    at import.
    """
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = Index(load_chunks(), LocalEmbedder(),
                                 cache_path=_CACHE_PATH)
    return _default


def search(query: str, k: int = 3) -> list[Chunk]:
    """Top-k documentation chunks for `query`, each with source and heading."""
    return get_index().search(query, k=k)
