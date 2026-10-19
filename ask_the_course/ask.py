"""Asker for ask-the-course.

Loads index.json, embeds the question via OpenRouter's
openai/text-embedding-3-small endpoint, retrieves the top-k chunks
by cosine similarity, sends them to minimax/minimax-m3 via OpenRouter's
chat-completions endpoint with a system prompt that enforces inline
citations and the exact refusal string, then prints the answer and
the chunk list.

Run from the project root:

    python -m ask_the_course.ask "What is the late submission policy?"

Optional flags:
    --no-retrieval   Skip embedding + retrieval; call the LLM with no course
                     context. Used to demonstrate that retrieval is doing the
                     work.
    --top-k N        Number of chunks to retrieve (default 5).

Requires the OPENROUTER_API_KEY environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests

# ---- paths ----

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = PROJECT_ROOT / "index.json"

# ---- model ----

EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIM = 1536
GENERATIVE_MODEL = "minimax/minimax-m3"
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
EMBED_TIMEOUT_SECONDS = 60
CHAT_TIMEOUT_SECONDS = 120

# ---- refusal ----

REFUSAL_STRING = "I can't find that in the course documents."

# ---- prompt ----

SYSTEM_PROMPT = f"""You are a course assistant for CPSC 415 at Trinity College. \
You answer questions strictly using the course documents the user supplies \
in this conversation. Follow these rules:

1. Read every chunk the user provides.
2. If the chunks contain the answer, write a clear, concise answer that \
cites the pages you used by including the source file and section heading \
inline (e.g., "According to syllabus.md > Office Hours, ...").
3. If the chunks do not contain the answer to the user's question, reply \
with EXACTLY this string and nothing else:

{REFUSAL_STRING}

Do not guess. Do not use outside knowledge. Do not apologize. Do not \
prefix or suffix the refusal string with anything."""

USER_PROMPT_TEMPLATE = """Course chunks retrieved from the index:

{chunks}

---

Question: {question}

Answer using only the chunks above. If the answer is not in the chunks, \
reply with EXACTLY: {refusal}"""


@dataclass
class Chunk:
    file_path: str
    section_heading: str
    text: str
    embedding: np.ndarray


# ---- api key ----

def _get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit(
            "OPENROUTER_API_KEY is not set. Export it before running the asker."
        )
    return key


# ---- index loading ----

def _load_index() -> list[Chunk]:
    """Load index.json. Verifies model metadata matches expectations.

    Raises SystemExit on any mismatch — this is the guard against the
    embedding-dimension drift risk in plan.md.
    """
    if not INDEX_PATH.exists():
        sys.exit(
            f"index.json not found at {INDEX_PATH}. "
            f"Run `python -m ask_the_course.index` first."
        )

    with INDEX_PATH.open(encoding="utf-8") as f:
        index = json.load(f)

    model = index.get("embedding_model")
    if model != EMBEDDING_MODEL:
        sys.exit(
            f"index.json was built with model {model!r}, "
            f"but the asker expects {EMBEDDING_MODEL!r}. "
            "Re-run `python -m ask_the_course.index` to rebuild."
        )

    dim = index.get("embedding_dim")
    if dim != EMBEDDING_DIM:
        sys.exit(
            f"index.json has embedding_dim={dim}, expected {EMBEDDING_DIM}. "
            "Re-run the indexer."
        )

    chunks_data = index.get("chunks")
    if not isinstance(chunks_data, list) or not chunks_data:
        sys.exit("index.json has empty or malformed 'chunks' array.")

    chunks: list[Chunk] = []
    for c in chunks_data:
        try:
            embedding = np.array(c["embedding"], dtype=np.float64)
        except (KeyError, TypeError, ValueError) as e:
            sys.exit(f"malformed chunk in index.json: {e}")
        if embedding.shape != (EMBEDDING_DIM,):
            sys.exit(
                f"chunk {c.get('file_path', '?')} has embedding of wrong shape "
                f"{embedding.shape}, expected ({EMBEDDING_DIM},)"
            )
        chunks.append(
            Chunk(
                file_path=c["file_path"],
                section_heading=c["section_heading"],
                text=c["text"],
                embedding=embedding,
            )
        )
    return chunks


# ---- embedding ----

def _embed_question(text: str, api_key: str) -> np.ndarray:
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
        embedding = payload["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as e:
        sys.exit(f"unexpected embedding response shape: {payload!r} ({e})")
    if len(embedding) != EMBEDDING_DIM:
        sys.exit(f"unexpected embedding dim {len(embedding)}")
    return np.array(embedding, dtype=np.float64)


# ---- retrieval ----

def _retrieve(
    question_embedding: np.ndarray, chunks: list[Chunk], top_k: int
) -> list[tuple[Chunk, float]]:
    """Return up to top_k (chunk, cosine_similarity) sorted by score desc."""
    if not chunks or top_k <= 0:
        return []
    chunk_matrix = np.stack([c.embedding for c in chunks], axis=0)
    q_norm = float(np.linalg.norm(question_embedding))
    if q_norm == 0.0:
        sys.exit("question embedding has zero norm")
    c_norms = np.linalg.norm(chunk_matrix, axis=1)
    valid = c_norms > 0.0
    scores = np.full(len(chunks), -np.inf)
    scores[valid] = (
        chunk_matrix[valid] @ question_embedding / (c_norms[valid] * q_norm)
    )
    k = min(top_k, len(chunks))
    top_indices = np.argpartition(-scores, k - 1)[:k]
    top_sorted = sorted(top_indices.tolist(), key=lambda i: scores[i], reverse=True)
    return [(chunks[i], float(scores[i])) for i in top_sorted]


# ---- formatting ----

def _format_chunks_for_prompt(retrieved: list[tuple[Chunk, float]]) -> str:
    blocks = []
    for rank, (chunk, _score) in enumerate(retrieved, start=1):
        src = f"{chunk.file_path} > {chunk.section_heading}".strip(" >")
        blocks.append(f"[Chunk {rank} from {src}]\n{chunk.text}")
    return "\n\n".join(blocks)


def _format_chunk_list(retrieved: list[tuple[Chunk, float]]) -> str:
    lines = []
    for chunk, score in retrieved:
        lines.append(f"{score:.3f} [{chunk.file_path} > {chunk.section_heading}]")
    return "\n".join(lines)


# ---- chat ----

def _chat(messages: list[dict], api_key: str) -> str:
    response = requests.post(
        OPENROUTER_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": GENERATIVE_MODEL,
            "messages": messages,
            "stream": False,
            "temperature": 0,
        },
        timeout=CHAT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        sys.exit(f"unexpected chat response shape: {payload!r} ({e})")
    if content is None:
        # finish_reason may be "length" or a content filter tripped
        return ""
    return content


# ---- public api ----

def ask(
    question: str,
    top_k: int = 5,
    no_retrieval: bool = False,
) -> tuple[str, list[tuple[Chunk, float]]]:
    """Ask a question. Returns (answer, retrieved_chunks).

    retrieved_chunks is empty when no_retrieval=True.
    """
    api_key = _get_api_key()

    if no_retrieval:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}"},
        ]
        answer = _chat(messages, api_key)
        return answer, []

    chunks = _load_index()
    question_embedding = _embed_question(question, api_key)
    retrieved = _retrieve(question_embedding, chunks, top_k)
    formatted = _format_chunks_for_prompt(retrieved)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                chunks=formatted,
                question=question,
                refusal=REFUSAL_STRING,
            ),
        },
    ]
    answer = _chat(messages, api_key)
    return answer, retrieved


# ---- cli ----

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ask_the_course.ask",
        description="Ask a question about CPSC 415 using the indexed course pages.",
    )
    parser.add_argument("question", help="The question to ask.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of chunks to retrieve (default: 5).",
    )
    parser.add_argument(
        "--no-retrieval",
        action="store_true",
        help="Skip retrieval; call the LLM with no course context.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    answer, retrieved = ask(
        args.question,
        top_k=args.top_k,
        no_retrieval=args.no_retrieval,
    )
    print(answer)
    print()  # blank-line separator between answer and chunk list
    if args.no_retrieval:
        print("(retrieval disabled — no chunks displayed)")
    else:
        print(_format_chunk_list(retrieved))


if __name__ == "__main__":
    main()
