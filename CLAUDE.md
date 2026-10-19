# Project conventions

## What this repository is
A Python CLI tool (`ask_the_course`) and evaluation script implementing a RAG system for the CPSC 415 course corpus. It embeds course documents and retrieves them to answer questions with inline citations. Implements [spec.md](spec.md).

## Commands
```text
# build: pip install -e .
# run indexer: python -m ask_the_course.index
# run asker: python -m ask_the_course.ask "your question"
# run eval: python eval.py
```

## Conventions
- **Language**: Python 3.11+.

- **APIs**: Use OpenRouter for both embeddings (openai/text-embedding-3-small) and generation (minimax/minimax-m3) using the requests library.

- **Outputs**: The asker must print the retrieved chunks and their scores for every answer.

## Working rules

- This is the Week 4 introductory lab. Stages assigned: intent, spec, and plan.
  No branches or pull requests yet. Commit to main.
- Libraries and build tools are allowed (pip or uv, Gradle or Maven). Name
  each dependency in spec.md with the reason for it. A RAG framework such as
  LangChain, LangChain4j, or Spring AI is fine, but the program must print
  the chunks it retrieved and their scores for every answer.
- The documents are the course repository at ../ai-integration-course:
  syllabus.md, assignments/, and weeks/01 through weeks/03 (the course as it
  stood before this lab). Skip weeks/04. Never copy the pages into this repo.

## Common mistakes
- **Model Downloads**: Trying to download heavy local ML models (like sentence-transformers) instead of using OpenRouter API endpoints.

- **Eval Brittle Matching**: Using strict sentence-level substring matching in evaluations. The model's markdown formatting (e.g., bolding or bullet points) breaks this; use word-set recall (≥50% recall) instead.

- **Corpus Filtering**: Using a denylist for the indexer instead of a strict whitelist. The indexer must explicitly whitelist syllabus.md, assignments/, and weeks/01..03 to prevent accidentally indexing root-level READMEs or future weeks.

- **Stale Page Refusals**: Misclassifying stale-page runs as "out-of-scope" in the eval script rather than handling them as "observation only."--
