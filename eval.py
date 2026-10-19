"""Eval script for ask-the-course.

Reads questions.json (five entries per spec behavior #10: three
factual, one multi-page, one out-of-scope) and runs each question
twice — once with retrieval and once without — appending every run's
question id, text, kind, mode, model answer, and chunk list to
CHECKS.md. Behavior #11 marks each run pass / wrong answer / refused.

Run from the project root:

    python eval.py

Optionally appends the stale-question observation (spec behavior #12):

    python eval.py --stale
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from ask_the_course.ask import REFUSAL_STRING, ask

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
STALE_QUESTION_PATH = Path(__file__).parent / "stale_question.json"
CHECKS_PATH = Path(__file__).parent / "CHECKS.md"


# ---- question loading ----

def _load_questions(path: Path, *, require_expected: bool = True) -> list[dict]:
    if not path.exists():
        sys.exit(f"{path} not found")
    with path.open(encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            sys.exit(f"{path} is not valid JSON: {e}")
    if not isinstance(data, list) or not data:
        sys.exit(f"{path} must be a non-empty list of question objects")
    for q in data:
        for required in ("id", "text", "kind"):
            if required not in q:
                sys.exit(f"{path} entry missing {required!r}: {q!r}")
        if require_expected and "expected" not in q:
            sys.exit(f"{path} entry missing 'expected': {q!r}")
    return data


# ---- verdict ----

_WORD_RE = __import__("re").compile(r"[^a-z0-9]+")


def _word_set(text: str) -> set[str]:
    """Lowercase, drop non-alphanumeric, split into word tokens (>=2 chars)."""
    norm = _WORD_RE.sub(" ", text.lower())
    return {w for w in norm.split() if len(w) >= 2}


def _verdict(question: dict, answer: str, mode: str) -> str:
    """Decide answered correctly / answered incorrectly / refused.

    Spec behavior #11 names these three verdict labels exactly.
    factual / multi-page: word-recall on normalized text (robust to
    markdown formatting the model adds around citations). out-of-scope:
    answered correctly iff the model's first non-blank line is exactly
    the refusal string. stale-page has no expected answer; we just
    record the observation.
    """
    kind = question["kind"]
    first_line = next(
        (ln for ln in answer.splitlines() if ln.strip()), ""
    ).strip()

    # The refusal string applies regardless of kind: out-of-scope is
    # answered correctly when the model refuses; factual/multi-page
    # that get refused are flagged "refused" (the model had no answer).
    if first_line == REFUSAL_STRING:
        if kind == "out-of-scope":
            return "answered correctly"
        if kind == "stale-page" or "expected" not in question:
            return "observation only (refused)"
        return "refused"

    if kind == "out-of-scope":
        # The model gave a real answer instead of refusing — wrong.
        return "answered incorrectly"

    if kind == "stale-page" or "expected" not in question:
        return "observation only"

    # factual / multi-page — word-recall on normalized text
    expected_words = _word_set(question["expected"])
    answer_words = _word_set(answer)
    if not expected_words:
        return "non-conforming response"
    recall = len(expected_words & answer_words) / len(expected_words)
    if recall >= 0.5:
        return "answered correctly"
    return f"answered incorrectly (recall {recall:.0%} of expected words)"


# ---- chunk formatting (mirrors ask_the_course.ask._format_chunk_list) ----

def _format_chunks(retrieved) -> str:
    return "\n".join(
        f"{score:.3f} [{chunk.file_path} > {chunk.section_heading}]"
        for chunk, score in retrieved
    )


# ---- run template ----

_RUN_SEP = "\n---\n\n"


def _format_run(
    timestamp: str,
    question: dict,
    mode: str,
    answer: str,
    chunk_lines: str,
    verdict: str,
) -> str:
    parts = [
        f"## Run {timestamp} — {question['id']} ({question['kind']}) — {mode}",
        "",
        f"**Question:** {question['text']}",
        "",
    ]
    if "expected" in question:
        parts.extend([f"**Expected:** {question['expected']}", ""])
    else:
        parts.extend(["**Expected:** (stale-page observation — see chunks)", ""])
    parts.extend([
        "**Answer:**",
        "",
        (answer.rstrip() if answer else "(empty)"),
        "",
    ])
    if mode == "with-retrieval":
        parts.extend(["**Chunks:**", "", chunk_lines or "(none)", ""])
    else:
        # Spec behavior #9: no-retrieval prints a one-line note instead
        # of a chunk list, since no chunks were retrieved.
        parts.extend([
            "**Retrieval:** (retrieval disabled — no chunks displayed)",
            "",
        ])
    parts.append(f"**Verdict:** {verdict}")
    parts.append("")
    return "\n".join(parts) + _RUN_SEP


# ---- run loop ----

def _run_one(question: dict, mode: str) -> tuple[str, str, str]:
    """Run a single question in a single mode. Returns (answer, chunks, verdict)."""
    no_retrieval = mode == "no-retrieval"
    try:
        answer, retrieved = ask(question["text"], no_retrieval=no_retrieval)
    except Exception as e:
        answer = f"(error: {type(e).__name__}: {e})"
        retrieved = []
    chunks = _format_chunks(retrieved) if mode == "with-retrieval" else ""
    verdict = _verdict(question, answer, mode)
    return answer, chunks, verdict


def _write_run(
    f, timestamp: str, question: dict, mode: str,
    answer: str, chunks: str, verdict: str,
) -> None:
    f.write(_format_run(timestamp, question, mode, answer, chunks, verdict))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="eval")
    parser.add_argument(
        "--stale",
        action="store_true",
        help=(
            "Run only stale_question.json once (with retrieval) and append. "
            "Used for spec behavior #12 — the stale-page observation."
        ),
    )
    args = parser.parse_args(argv)

    if not CHECKS_PATH.exists():
        CHECKS_PATH.write_text("# ask-the-course eval log\n\n", encoding="utf-8")

    with CHECKS_PATH.open("a", encoding="utf-8") as f:
        if args.stale:
            if not STALE_QUESTION_PATH.exists():
                sys.exit(
                    f"--stale was passed but {STALE_QUESTION_PATH} was not found. "
                    "Create it before re-running."
                )
            stale_questions = _load_questions(STALE_QUESTION_PATH, require_expected=False)
            total_runs = 0
            for q in stale_questions:
                timestamp = datetime.datetime.now().isoformat(timespec="seconds")
                answer, chunks, verdict = _run_one(q, "with-retrieval")
                _write_run(f, timestamp, q, "with-retrieval", answer, chunks, verdict)
                print(f"{q['id']} (with-retrieval): {verdict}")
                total_runs += 1
            print(f"Appended {total_runs} run(s) to {CHECKS_PATH}")
            return

        questions = _load_questions(QUESTIONS_PATH)
        total_runs = len(questions) * 2
        for q in questions:
            for mode in ("with-retrieval", "no-retrieval"):
                timestamp = datetime.datetime.now().isoformat(timespec="seconds")
                answer, chunks, verdict = _run_one(q, mode)
                _write_run(f, timestamp, q, mode, answer, chunks, verdict)
                print(f"{q['id']} ({mode}): {verdict}")

    print(f"Appended {total_runs} run(s) to {CHECKS_PATH}")


if __name__ == "__main__":
    main()
