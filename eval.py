"""Eval script for ask-the-course.

Step 1 stub. The full eval loop (read questions.json, run each question
twice via ask_the_course.ask, append to CHECKS.md) lands in plan.md
step 7. For now this stub just defines the paths and the refusal string
so they live in one place from day one.
"""

from pathlib import Path

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
STALE_QUESTION_PATH = Path(__file__).parent / "stale_question.json"
CHECKS_PATH = Path(__file__).parent / "CHECKS.md"

REFUSAL_STRING = "I can't find that in the course documents."


def main() -> None:
    """Placeholder for the eval loop. Filled in by plan step 7."""
    print(
        f"eval.py stub — will read {QUESTIONS_PATH.name} "
        f"and append to {CHECKS_PATH.name}"
    )


if __name__ == "__main__":
    main()
