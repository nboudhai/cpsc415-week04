# Spec

<!-- The agent writes this from the approved intent. You validate it against the intent.
     If the spec and the intent disagree, the intent wins until you change the intent. -->

## Intent
Implements [`intent/ask-the-course.md`](intent/ask-the-course.md).

## Components

### Indexer
- **What it does:** Reads the course's Markdown pages from
  `../ai-integration-course/{syllabus.md, assignments/, weeks/01..03}` (skipping
  `weeks/04`), splits them into chunks by Markdown header, embeds each chunk
  by calling OpenRouter's `openai/text-embedding-3-small` embeddings endpoint
  via `requests`, and writes a JSON index (`index.json` at the project root)
  listing every chunk with its file path, top-level section heading, text,
  and embedding vector.
- **Language:** Python 3.11+. **Why:** Python has the libraries the
  spec uses (LangChain text splitters, `requests`, NumPy) and the lab is a
  single-shot tool, so the lighter setup beats Java. Compared to Java +
  Spring AI: Spring AI is fine for a service, but the boilerplate (Gradle,
  application context, beans) is overkill here. Compared to Java +
  LangChain4j: a thinner ecosystem for a one-off CLI.
- **Model:** `openai/text-embedding-3-small` (via OpenRouter). **Why:**
  Matches the Week 4 setup verification, avoids heavy local ML downloads
  (like a `sentence-transformers` model), and runs quickly through the
  OpenRouter API we already configured. Cheap compared to the frontier
  `text-embedding-3-large` ($0.13/1M tokens): on the MTEB retrieval
  benchmark `text-embedding-3-small` scores 62.3 vs. 64.6 for the large
  variant, and on a focused, small-vocabulary course corpus the gap is
  small.
- **Interfaces:**
  - **Input:** a fixed corpus path (`../ai-integration-course/`).
  - **Output:** `index.json` at the project root, with one record per chunk:
    `{file_path, section_heading, text, embedding}`.
  - **CLI:** `python -m ask_the_course.index` (re)builds the index
    from scratch. Re-running overwrites `index.json`.
- **Dependencies:**
  - `langchain-text-splitters` — Markdown-aware splitting that carries the heading into chunk metadata.
  - `requests` — to make REST API calls to the OpenRouter embeddings endpoint.

### Asker
- **What it does:** Takes a single question as a CLI argument, loads
  `index.json`, embeds the question with the same model the indexer used,
  retrieves the top-k most similar chunks by cosine similarity, sends those
  chunks to the LLM with a system prompt that enforces inline citations or
  the exact refusal string, then prints the answer followed by a chunk list
  (one line per chunk: similarity score and `[file_path > section heading]`).
  With `--no-retrieval`, the asker skips retrieval entirely and calls the
  LLM with no course context (used to demonstrate that retrieval is doing
  the work).
- **Language:** Python 3.11+. **Why:** same reasoning as the indexer — one
  language for the whole tool, faster iteration than Java for a CLI.
- **Model:** `minimax/minimax-m3` (generative, via OpenRouter). **Why:**
  Routed by OpenRouter for the Week 4 lab setup, follows strict format
  instructions reliably (the exact refusal string matters here), and is
  cheap for a small corpus. Compared to a heavier frontier model
  (`claude-sonnet-5-5` or similar): frontier models are better at
  synthesizing across multiple retrieved chunks for the multi-page policy
  question, but the gap narrows on a small, well-scoped corpus and a
  strict output format. Use `minimax/minimax-m3` as the default; if the
  multi-page eval question is unsatisfactory, swap to a frontier model
  and re-run.
- **Interfaces:**
  - **Input:** a positional `question` argument; flags `--no-retrieval` and
    `--top-k` (default 5); env var `OPENROUTER_API_KEY` for the embedding
    and chat-completion API calls.
  - **Output on stdout:**
    1. The LLM's answer (possibly with inline citations).
    2. A blank line.
    3. A chunk list: one line per retrieved chunk, formatted as
       `<score:0.000> [file_path > section heading]`,
       e.g. `0.812 weeks/03/lab.md > 4. The second model`.
  - **Files read:** `index.json` (produced by the indexer).
  - **Files written:** none.
  - **Supporting script:** `eval.py` reads `questions.json` (shape:
    `[{id, text, kind}]` where `kind ∈ {"factual", "multi-page",
    "out-of-scope", "stale-page"}`), runs the asker once per question
    with retrieval and once per question without, and appends every run's
    input question, model answer, and chunk list to `CHECKS.md`.
- **Dependencies:**
  - `requests` — to make HTTP calls to OpenRouter for both the chat completion and the question embedding.
  - `numpy` — for calculating cosine similarity between the question embedding and chunk embeddings.

## Behavior

1. The indexer reads every `.md` file under
   `../ai-integration-course/{syllabus.md, assignments/, weeks/01..03}` and
   skips `weeks/04` if present.
2. The indexer splits each page by Markdown headers and attaches the
   top-level heading as a `section_heading` field on every chunk it
   produces. Sections longer than ~1000 characters are split further with
   a 200-character overlap, with the original `section_heading` preserved.
3. The indexer embeds every chunk via OpenRouter's
   `openai/text-embedding-3-small` endpoint and writes `index.json`
   containing `{file_path, section_heading, text, embedding}` per chunk.
4. The asker accepts one question as a positional argument and (by
   default) prints the answer followed by the chunk list described in the
   Asker's Interfaces, in that order, separated by a blank line.
5. The asker embeds the question via OpenRouter's
   `openai/text-embedding-3-small` endpoint (the same model the indexer
   used) and retrieves the top-k chunks by cosine similarity
   (default k=5).
6. The asker sends the retrieved chunks to the LLM with a system prompt
   that:
   - instructs the model to answer only from the provided chunks,
   - instructs the model to cite the pages it used inline in the answer,
   - instructs the model that, if the chunks do not contain the answer,
     it must reply with exactly `I can't find that in the course documents.`
     and nothing else.
7. When the model returns the refusal string, the asker prints it
   verbatim — no prefix, no suffix, no apology — followed by the chunk
   list, so the refusal is auditable.
8. Every retrieved chunk is printed with its similarity score and source
   in the format `[file_path > section heading]`, e.g.
   `0.812 weeks/03/lab.md > 4. The second model`.
9. With `--no-retrieval`, the asker sends the question to the LLM with no
   course context and prints the model's answer followed by a one-line
   note that retrieval was disabled. No chunk list is printed, because no
   chunks were retrieved.
10. `eval.py` reads `questions.json` (exactly five entries: three `factual`,
    one `multi-page`, one `out-of-scope`) and runs the asker once per
    question with retrieval and once per question without, appending each
    run to `CHECKS.md` with: question id and text, `kind`, mode
    (`with-retrieval` or `no-retrieval`), the model's full answer, and the
    chunk list when applicable.
11. `CHECKS.md` records, for each question, whether the with-retrieval
    run answered correctly, answered incorrectly, or refused; and what the
    no-retrieval run produced. A question is "passed with retrieval" if
    its answer matches the developer's hand-written expected answer in
    `questions.json` (`expected` field), or matches the exact refusal
    string for `kind = "out-of-scope"`.
12. A `stale-page` eval question is also recorded in `CHECKS.md`: a
    question where both `weeks/01` and `weeks/03` chunks are expected to
    be retrieved. The eval records the LLM's answer and which chunks it
    cited, and the developer appends a short note in `CHECKS.md`
    describing one theoretical way a RAG system could prefer the newer
    page (e.g. attaching last-modified dates to chunk metadata and using
    them as a tie-breaker). No code change is required.

## Failure handling

- **Empty or whitespace-only question:** the asker prints a usage message
  to stderr and exits non-zero without calling the LLM.
- **`index.json` missing:** the asker prints a clear error pointing at
  the indexer command and exits non-zero.
- **`OPENROUTER_API_KEY` missing or invalid:** the indexer and asker
  check the env var before any HTTP call and exit non-zero with a clear
  "set `OPENROUTER_API_KEY`" message if it is not set.
- **OpenRouter API call fails** (network, auth, rate limit, 5xx, model
  unavailable, timeout): the indexer writes `index.json` only after the
  full embed loop succeeds (so a partial index is never left on disk);
  the asker prints the error to stderr and exits non-zero. The eval
  script catches this per question and records the failure in
  `CHECKS.md`, so a partial run is still auditable.
- **LLM returns something other than the answer or the exact refusal
  string:** the asker prints whatever the LLM returned, then prints the
  chunk list as usual. The eval script flags this in `CHECKS.md` as
  "non-conforming response" rather than treating it as a pass.
- **A Markdown page has no headers:** the indexer treats the whole page
  as one chunk with `section_heading = ""` so retrieval still works and
  the citation format degrades to `[file_path > ]`.
- **`weeks/04` is present in the corpus directory:** the indexer
  explicitly skips it.

## Cost estimate

- **Embeddings:** OpenRouter's `openai/text-embedding-3-small` is priced
  at roughly **$0.02 per 1M tokens** (matches OpenAI direct). The course
  corpus is small (under ~100k tokens), so the index build costs about
  **$0.000002** once. Each question embeds ~50 tokens, so the per-question
  embedding cost is negligible (~$0.0000001).
- **LLM, with retrieval, per question:** input ≈ 5 chunks × ~250 tokens
  + ~250 token system prompt + ~50 token question = ~1.55k tokens in;
  ~200 tokens out. Pricing for `minimax/minimax-m3` on OpenRouter should
  be confirmed against OpenRouter's current price list; assuming a
  cheap-tier rate on the order of $0.20 in / $1 out per 1M tokens, this
  works out to roughly **$0.0000005 per question**. (Replace with the
  actual OpenRouter rate once verified.)
- **LLM, no retrieval, per question:** input ≈ 300 tokens; ~200 tokens
  out. Roughly half the with-retrieval cost.
- **Per eval run** (10 calls = 5 questions × 2 modes): well under
  $0.001 even with a generous price assumption.
- **A semester of grading** (say 20 eval runs): well under $0.01.

## Out of scope

- Programmatic resolution of stale page conflicts. The "stale page"
  scenario is observed in `CHECKS.md` and a theoretical fix is described;
  nothing is implemented.
- A web UI, multi-user service, or any deployment.
- Training or fine-tuning a model.
- Course content outside `../ai-integration-course/{syllabus.md,
  assignments/, weeks/01..03}`.
- Conversation memory across questions. Each invocation of the asker is
  independent.
- Cross-encoder re-ranking, hybrid (BM25 + dense) retrieval, or other
  retrieval improvements beyond top-k cosine similarity.
- Persisting chat history, evaluation history, or any state between
  invocations of the asker beyond `index.json` and `CHECKS.md`.
