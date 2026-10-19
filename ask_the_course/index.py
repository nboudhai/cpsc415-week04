"""Indexer for ask-the-course.

Reads the course's Markdown pages from ../ai-integration-course,
chunks them by Markdown header (with a 1000-char cap and 200-char
overlap for long sections), embeds each chunk via OpenRouter's
openai/text-embedding-3-small endpoint, and writes index.json at the
project root with model metadata so the asker can verify on load
(see plan.md risk "Embedding dimension drift / index version skew").

Run from the project root:

    python -m ask_the_course.index

Requires the OPENROUTER_API_KEY environment variable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

# ---- paths ----

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = (PROJECT_ROOT.parent / "ai-integration-course").resolve()
INDEX_PATH = PROJECT_ROOT / "index.json"

# ---- model ----

EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIM = 1536
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
EMBED_TIMEOUT_SECONDS = 60

# ---- chunking ----

MAX_CHUNK_CHARS = 1000
CHUNK_OVERLAP = 200
_HEADERS_TO_SPLIT_ON = [("#", "Header 1")]

# ---- corpus filter ----

# Per spec: include only syllabus.md, assignments/, and weeks/01..03.
# Anything else at the corpus root (README.md, slides/, examples/,
# scripts/) is out of scope.
_ALLOWED_TOP_LEVEL = {"syllabus.md", "assignments", "weeks"}
_MIN_INCLUDED_WEEK = 1
_MAX_INCLUDED_WEEK = 3


def _should_include(rel_path: Path) -> bool:
    """Whitelist: only syllabus.md, assignments/*, and weeks/{1,2,3}/**."""
    parts = rel_path.parts
    if not parts:
        return False
    top = parts[0]
    if top == "syllabus.md":
        return len(parts) == 1  # the file at the corpus root, not a subdirectory
    if top == "assignments":
        return True  # whole directory
    if top == "weeks":
        if len(parts) < 2:
            return False
        try:
            week_num = int(parts[1])
        except ValueError:
            return False
        return _MIN_INCLUDED_WEEK <= week_num <= _MAX_INCLUDED_WEEK
    return False  # README.md, slides/, examples/, scripts/, .git/, etc.


def _collect_corpus_files(corpus_root: Path) -> list[Path]:
    if not corpus_root.exists():
        sys.exit(f"corpus not found at {corpus_root}")
    files = sorted(
        path
        for path in corpus_root.rglob("*.md")
        if _should_include(path.relative_to(corpus_root))
    )
    if not files:
        sys.exit(f"no .md files found under {corpus_root}")
    return files


# ---- chunking ----

_md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS_TO_SPLIT_ON)
_long_splitter = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CHUNK_CHARS,
    chunk_overlap=CHUNK_OVERLAP,
)


def _chunk_page(text: str) -> list[tuple[str, str]]:
    """Split a Markdown page into (section_heading, chunk_text) tuples.

    The section_heading is the most recent top-level ('# ...') heading
    covering the chunk. Pages with no top-level heading produce a single
    chunk with section_heading = "".
    """
    docs = _md_splitter.split_text(text)
    chunks: list[tuple[str, str]] = []
    for doc in docs:
        heading = doc.metadata.get("Header 1", "")
        body = doc.page_content.strip()
        if not body:
            continue
        if len(body) <= MAX_CHUNK_CHARS:
            chunks.append((heading, body))
        else:
            for sub in _long_splitter.split_text(body):
                sub = sub.strip()
                if sub:
                    chunks.append((heading, sub))
    return chunks


# ---- embedding ----

def _get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit(
            "OPENROUTER_API_KEY is not set. Export it before running the indexer."
        )
    return key


def _embed_text(text: str, api_key: str) -> list[float]:
    """Embed a single chunk via OpenRouter; returns a list of floats."""
    response = requests.post(
        OPENROUTER_EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": EMBEDDING_MODEL, "input": text},
        timeout=EMBED_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    try:
        return payload["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as e:
        sys.exit(f"unexpected embedding response shape: {payload!r} ({e})")


# ---- build ----

def build_index() -> dict:
    api_key = _get_api_key()
    files = _collect_corpus_files(CORPUS_ROOT)
    print(f"Found {len(files)} .md file(s) under {CORPUS_ROOT}", file=sys.stderr)

    chunks: list[dict] = []
    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"  skip {file_path}: {e}", file=sys.stderr)
            continue

        rel_path = file_path.relative_to(CORPUS_ROOT).as_posix()
        page_chunks = _chunk_page(text)
        print(f"  {rel_path}: {len(page_chunks)} chunk(s)", file=sys.stderr)

        for heading, chunk_text in page_chunks:
            try:
                embedding = _embed_text(chunk_text, api_key)
            except requests.HTTPError as e:
                body = ""
                try:
                    body = e.response.text if e.response is not None else ""
                except Exception:
                    pass
                sys.exit(f"embed failed for {rel_path}: {e} {body}")

            if len(embedding) != EMBEDDING_DIM:
                sys.exit(
                    f"unexpected embedding dim {len(embedding)} for {rel_path}; "
                    f"expected {EMBEDDING_DIM}"
                )

            chunks.append(
                {
                    "file_path": rel_path,
                    "section_heading": heading,
                    "text": chunk_text,
                    "embedding": embedding,
                }
            )

    return {
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "chunks": chunks,
    }


def main() -> None:
    index = build_index()
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"Wrote {len(index['chunks'])} chunk(s) to {INDEX_PATH}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
