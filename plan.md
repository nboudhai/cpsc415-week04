# Plan

<!-- The agent proposes this from the spec. Interrogate it ("what could break?") and approve
     before any code is written. Update it when the plan changes. -->

## Files to create or change
| File | Purpose |
|---|---|
| `pyproject.toml` | Project metadata and pinned dependencies (`langchain-text-splitters`, `requests`, `numpy`). Replaces ad-hoc dependency management. `requests` is the only HTTP client; the `anthropic` SDK and `sentence-transformers` are intentionally not used (see spec.md). |
| `.gitignore` | Add `__pycache__/`, `*.pyc`, `.env`, and any local-only state. Keep `index.json` tracked so the grader can re-use it; if it grows too large, switch to git-lfs. |
| `ask_the_course/__init__.py` | Marks the package. Empty. |
| `ask_the_course/index.py` | The indexer. Reads `../ai-integration-course/{syllabus.md, assignments/, weeks/01..03}`, chunks by Markdown header (with a 1000-char cap and 200-char overlap), embeds each chunk by calling OpenRouter's `openai/text-embedding-3-small` endpoint via `requests`, writes `index.json` at the project root. Run as `python -m ask_the_course.index`. |
| `ask_the_course/ask.py` | The asker. Loads `index.json`, embeds the question by calling OpenRouter's `openai/text-embedding-3-small` endpoint via `requests` (same model the indexer used), retrieves top-k=5 by cosine similarity, calls `minimax/minimax-m3` via OpenRouter's chat-completions endpoint with the system prompt described in spec behavior #6, prints the answer and chunk list. Supports `--no-retrieval` and `--top-k`. Run as `python -m ask_the_course.ask "..."`. Reads `OPENROUTER_API_KEY` from the environment. |
| `questions.json` | Five entries: three `factual`, one `multi-page`, one `out-of-scope`. Each entry is `{id, text, kind, expected}`. `expected` is the developer's hand-written answer (or the exact refusal string for `out-of-scope`). |
| `stale_question.json` | A single object `{id, text, kind: "stale-page"}`. Hand-picked so retrieval should bring back chunks from both `weeks/01` and `weeks/03`. Kept separate from `questions.json` because it is one observation, not part of the 5-question eval. |
| `eval.py` | Reads `questions.json` and `stale_question.json`. Runs every question in `questions.json` twice (with and without retrieval) and runs `stale_question.json` once. Appends each run (question id/text, kind, mode, model answer, chunk list) to `CHECKS.md`. |
| `CHECKS.md` | Eval log. Created empty; populated by `eval.py`. |
| `plan.md` | This file. Overwritten. |
| `spec.md` | Already updated. No further change. |
| `intent/ask-the-course.md` | Already committed. No further change. |
| `CLAUDE.md` | Already committed. No further change. |

## Order of work

1. **Skeleton.** Create `pyproject.toml` with the three pinned deps
   (`langchain-text-splitters`, `requests`, `numpy`), the
   `ask_the_course/` package directory with an empty `__init__.py`, and the
   top-level `eval.py` stub. Install with `pip install -e .`. Confirm
   `python -c "import ask_the_course"` works. Confirm `OPENROUTER_API_KEY`
   is exported in the dev shell so step 2 can call OpenRouter without an
   auth error.
2. **Indexer.** Implement `ask_the_course/index.py`. The embedder is a
   small wrapper around the OpenRouter embeddings endpoint
   (`POST https://openrouter.ai/api/v1/embeddings`) using
   `openai/text-embedding-3-small`. Run it against the real corpus and
   produce `index.json`. Eyeball a handful of chunks (one from
   `syllabus.md`, one from `assignments/`, one from `weeks/03`) to confirm
   the file paths and section headings are right.
3. **Asker — happy path.** Implement `ask_the_course/ask.py` for the
   default (with-retrieval) mode. The chat call goes through OpenRouter's
   chat-completions endpoint with model `minimax/minimax-m3`. Hand-test
   one factual question and confirm the answer is grounded and the chunk
   list is populated.
4. **Asker — refusal path.** Hand-test one out-of-scope question and
   confirm the model emits the exact refusal string. If it does not,
   tighten the system prompt and re-test before moving on.
5. **Asker — `--no-retrieval`.** Implement the flag. Hand-test one
   factual question in this mode and confirm the model answers from
   parametric knowledge (and therefore wrong for course-specific facts).
   This is what makes the comparison in step 8 meaningful.
6. **`questions.json`.** Draft five entries based on what's actually in
   the corpus (re-read the index from step 2 if needed). Pick
   course-specific facts the model is unlikely to know without
   retrieval (specific dates, policy numbers, assignment titles) so
   the no-retrieval run fails for the right reason.
7. **`eval.py`.** Wire it to read `questions.json`, run each question
   twice, and append to `CHECKS.md` with a fixed per-run template
   (question id, text, kind, mode, model answer, chunk list).
8. **First eval run.** Run `python eval.py`. Open `CHECKS.md` and verify
   the 10 runs (5 × 2 modes) are all there, the with-retrieval runs
   match `expected` for the three factual questions and the multi-page
   question, the with-retrieval refusal matches the literal string,
   and the no-retrieval runs do **not** match `expected` for the
   factual/multi-page questions.
9. **Stale-page run.** Pick a question that pulls chunks from both
   `weeks/01` and `weeks/03` (verify by reading the chunk list), save
   it in `stale_question.json`, run `python eval.py --stale` (or
   whichever trigger is wired), append to `CHECKS.md`, and write a
   short note describing one theoretical fix (last-modified metadata
   on chunks, used as a tie-breaker).
10. **Final pass.** Re-read `spec.md` behaviors #1–#12 and confirm each
    is satisfied by what's in `CHECKS.md`. If any are not, loop back to
    the step that owns them.

## Risks

- **Corpus path is relative (`../ai-integration-course/`).** Assumption:
  the project is run from its own root, so the relative path resolves.
  Blast radius if wrong: the indexer raises on the first file read and
  nothing downstream works. Mitigation: compute the corpus path from
  `__file__` inside `index.py`, not from `os.getcwd()`.

- **`OPENROUTER_API_KEY` is not set or is invalid.** Assumption: the
  dev shell has `OPENROUTER_API_KEY` exported before any tool runs.
  Blast radius: every indexer and asker call fails with a 401, the
  eval script records nothing useful, the asker fails to embed the
  question. Mitigation: check the env var at the top of `index.py` and
  `ask.py` and exit with a clear "set `OPENROUTER_API_KEY`" message
  before any HTTP call.

- **Embedding endpoint errors (wrong URL, wrong shape, response
  surprises).** Assumption: the request hits
  `https://openrouter.ai/api/v1/embeddings` with an OpenAI-style body
  `{"model": "openai/text-embedding-3-small", "input": "..."}` and the
  response comes back as `{"data": [{"embedding": [...]}]}`. Failure
  modes: wrong endpoint (`/chat/completions` by mistake), wrong shape
  (missing `model` / `input`), or response wrapped in an unexpected
  envelope (data under a different key, embedding returned as a string
  rather than a list). Blast radius: HTTP 4xx, `KeyError`, or
  `TypeError`; nothing gets embedded. Mitigation: build the request
  body from one constant and the response from
  `r.json()["data"][0]["embedding"]`; in debug mode, print the raw
  response status, body, and the resulting embedding's length.

- **Embedding dimension drift / index version skew (silent failure).**
  Assumption: every chunk in `index.json` was embedded with the same
  model the asker uses to embed the question
  (`openai/text-embedding-3-small`, 1536 dims). Failure mode: the index
  was rebuilt with a different model and old data wasn't cleared, or
  someone hand-edits `index.json`, and the two vector spaces no longer
  match. Blast radius: cosine similarity still runs but every score is
  near zero and the top-k list is irrelevant content. **This is the
  highest-impact silent failure in the system.** Mitigation: store the
  embedding model name inside `index.json`; on load, the asker compares
  that name to its own constant and refuses to run if they differ.

- **OpenRouter API call fails (network, 429, 5xx, timeout).**
  Assumption: OpenRouter is reachable from the dev machine, rate limits
  are well above our use, and the chosen models are available.
  Blast radius: indexer fails partway through (partial `index.json`);
  asker fails for that question. Mitigation: in `index.py`, write
  `index.json` only after the full embed loop succeeds; in `eval.py`,
  catch HTTP errors per question and record the failure in `CHECKS.md`
  so a partial run is still auditable.

- **`minimax/minimax-m3` model availability.** Assumption: the model
  is reachable through OpenRouter at the time of the run. Failure mode:
  the model has been renamed, deprecated, or routed to a different
  upstream. Blast radius: every asker call returns a 404 / "model not
  found." Mitigation: catch the specific error in `ask.py` and print a
  clear "model unavailable" message; the eval script records this in
  `CHECKS.md`.

- **Chat completion response surprises.** Several distinct failure
  modes against OpenRouter's chat-completions endpoint with
  `minimax/minimax-m3`:
  - **Streaming by default.** Some models stream SSE even without
    `stream: true`. `response.json()` then returns an incomplete body.
  - **`finish_reason: "length"` or `content: null`.** The model hit a
    token cap or a content filter tripped; the answer is empty or
    truncated.
  - **Model wraps the answer in JSON or a Markdown fence.** Some chat
    models default to JSON mode or fence answers in ```` ``` ````.
  - **OpenRouter adds extra fields.** `id`, `model`, `usage`,
    `transforms` are present in addition to `choices`; strict parsing
    chokes on the extras.
  Blast radius: empty answer above the chunk list, refusal-shaped
  non-refusal, or traceback in the asker. Mitigation: parse the
  response defensively (only read `choices[0].message.content`,
  ignore everything else); in debug mode, print the full response body;
  the eval script flags "non-conforming response" rather than treating
  it as a pass.

- **Prompt construction errors.** Two failure modes:
  - **Context length overflow.** Five chunks × ~250 tokens + ~250 token
    system prompt + ~50 token question ≈ 1.55k in, well under any
    window, but if `--top-k` is bumped to 20 or the system prompt
    grows, OpenRouter returns HTTP 400 with
    `context_length_exceeded`.
  - **System prompt dropped or in the wrong role.** OpenRouter uses
    OpenAI's `messages: [{role: "system", ...}, {role: "user", ...}]`
    shape. If the system prompt is sent as `user`, behavior changes
    silently: the model answers less strictly, sometimes refuses when
    it shouldn't, sometimes invents citations because the "cite pages
    you used" instruction never applied.
  Blast radius: HTTP 400, or the with-retrieval factual answers start
  looking like the no-retrieval answers. Mitigation: build the messages
  list from one helper that always puts the system prompt in
  `messages[0].role == "system"`; if `--top-k` is large, log the
  estimated input tokens before sending.

- **Output formatting drift.** Three failure modes that pass through
  the LLM call fine but break the printed format:
  - **Score precision.** Default Python float repr prints
    `0.8123456789` instead of the spec'd `0.812` (3 decimals).
  - **Special chars in `section_heading`.** A heading containing `>`
    (rare, but possible with HTML entities like `>`) makes the
    `[file_path > section heading]` citation ambiguous.
  - **Newlines in chunk text.** A chunk's `text` often contains `\n`;
    if it leaks into the chunk list line, the list visually wraps and
    breaks any downstream grep/sed.
  Blast radius: chunk list is visually wrong or unparseable. Mitigation:
  format scores with `f"{score:.3f}"`; the chunk-list line is built
  from `file_path`, the literal ` > `, and `section_heading` only —
  never from the chunk `text`.

- **Upstream provider drift through OpenRouter.** OpenRouter routes
  `minimax/minimax-m3` to whatever provider serves it. If that
  provider changes their output format, rate-limits, or routes, the
  asker's behavior changes without any code change. Blast radius:
  results vary across runs without any code change; same question,
  different answer. Mitigation: there is no code-level fix; just be
  ready to re-run the eval and treat `CHECKS.md` as a snapshot in time.

- **Model does not emit the exact refusal string.** Assumption:
  `minimax/minimax-m3` follows the system-prompt instruction to reply
  with exactly `I can't find that in the course documents.` Blast radius
  if wrong: the out-of-scope eval fails and the asker prints a near-miss
  string that won't auto-grade. Mitigation: spec failure handling
  already covers this — `eval.py` flags "non-conforming response"
  rather than silently passing — so we will see it in `CHECKS.md` and
  can iterate on the system prompt.

- **No-retrieval run accidentally passes a factual question.**
  Assumption: the chosen factual questions have answers the model
  cannot know without the corpus (specific dates, exact policy text,
  specific assignment names). Blast radius: the comparison in
  `CHECKS.md` doesn't prove retrieval is doing the work, which is the
  whole point of behavior #11. Mitigation: pick factual questions
  deliberately and verify in step 8 that the no-retrieval runs
  visibly miss `expected`.

- **`top-k=5` is too small for the multi-page policy question.**
  Assumption: the relevant chunks from both pages will all be in the
  top 5 by cosine similarity. Blast radius: the multi-page eval
  fails. Mitigation: spec already exposes `--top-k`; bump the default
  to 7 if the multi-page eval question misses a page.

- **Markdown heading detection is brittle.** Code fences containing `#`
  lines can be mis-read as headings; pages with no headers produce
  empty `section_heading` fields. Blast radius: citation format prints
  `[file_path > ]` for headerless pages, which is ugly but not
  catastrophic. Mitigation: spec failure handling already specifies
  the empty-heading fallback; verify by inspecting the index.

- **`CHECKS.md` format drift across runs.** Assumption: `eval.py` uses
  one template per run, consistently. Blast radius: the file becomes
  hard to read and verification slows down. Mitigation: define the
  template once in `eval.py`, never inline a run format in two places.

- **The stale-page question doesn't actually pull both weeks.**
  Assumption: a topic that recurs across `weeks/01` and `weeks/03`
  exists in this corpus (likely — the course builds on prior weeks).
  Blast radius: the experiment is invalid and the observation in
  `CHECKS.md` is misleading. Mitigation: before recording the
  answer, eyeball the chunk list and confirm both `weeks/01` and
  `weeks/03` appear; if not, pick a different question.

- **Windows path separators and line endings.** Assumption: the
  developer is on Windows (per environment) and the corpus uses
  forward slashes. Blast radius: relative-path joins break. Mitigation:
  use `pathlib.Path` everywhere and `os-independent` joins; verify on
  a Windows run before declaring the indexer done.

- **Course corpus is missing or has changed.** Assumption:
  `../ai-integration-course/` exists and is the version the developer
  intended to index. Blast radius: retrieval is silently wrong if the
  corpus has drifted since `index.json` was built. Mitigation: rebuild
  the index whenever the corpus changes; document this in the
  indexer CLI help text.

## Proof

1. **Skeleton — install and import.**
   - **Command (PowerShell):**
     ```powershell
     pip install -e .
     if ($?) { python -c "import ask_the_course" }
     if ($?) { if ($env:OPENROUTER_API_KEY) { "env ok" } else { "env MISSING" } }
     ```
   - **Expected:** all three commands exit `0`; the last prints `env ok`.
     On bash, replace `$?` with the previous exit code and `$env:OPENROUTER_API_KEY`
     with `$OPENROUTER_API_KEY`.

2. **Indexer — run and inspect shape.**
   - **Command (PowerShell):**
     ```powershell
     python -m ask_the_course.index
     echo "exit=$LASTEXITCODE"
     Test-Path index.json
     ```
   - **Expected:** exit code `0`; `index.json` exists at the project root.
   - **Shape check (one-liner):**
     ```powershell
     python -c "import json; d=json.load(open('index.json')); assert isinstance(d,list) and len(d)>0, 'empty or wrong shape'; r=d[0]; need={'file_path','section_heading','text','embedding'}; assert need<=r.keys(), f'missing keys: {need-set(r.keys())}'; assert isinstance(r['embedding'],list) and len(r['embedding'])==1536, f'wrong dim {len(r[\"embedding\"])}'; print(f'{len(d)} chunks; first file_path={r[\"file_path\"]!r}; first heading={r[\"section_heading\"]!r}')"
     ```
   - **Expected stdout:** `N chunks; first file_path='syllabus.md'; first heading='...'`
     (or similar — the exact first record depends on file walk order).
   - **What it proves:** the indexer hit OpenRouter successfully, returned
     1536-dim embeddings, split the corpus into chunks, and attached
     section headings.

3. **Asker — happy path (with retrieval).**
   - **Command (PowerShell):**
     ```powershell
     python -m ask_the_course.ask "What is the late policy on assignments?"
     echo "exit=$LASTEXITCODE"
     ```
     (Replace the question with any factual whose expected answer is in
     the corpus.)
   - **Expected:** exit code `0`. Output has three sections separated by
     blank lines:
     1. **Answer** (one or more lines), grounded in the corpus, with at
        least one inline citation to a course page.
     2. **Blank line.**
     3. **Chunk list** — exactly 5 lines (the default top-k), each
        formatted as `<score:0.000> [file_path > section heading]`, e.g.
        `0.812 weeks/03/lab.md > 4. The second model`.
   - **Format check:**
     ```powershell
     $out = python -m ask_the_course.ask "What is the late policy on assignments?"
     $lines = $out -split "`n"
     $chunkLines = $lines[2..($lines.Count - 1)]
     $chunkLines | ForEach-Object {
         if ($_ -notmatch '^\d\.\d{3} \[') { "FAIL on line: $_"; exit 1 }
     }
     "PASS — $($chunkLines.Count) chunk lines, all formatted as score + bracket"
     ```
   - **What it proves:** the asker loaded `index.json`, embedded the
     question through OpenRouter, retrieved top-k=5 chunks, called the
     chat-completions endpoint with `minimax/minimax-m3`, got a real
     answer back, and printed the spec'd citation format.

4. **Asker — refusal path (with retrieval).**
   - **Command (PowerShell):**
     ```powershell
     $out = python -m ask_the_course.ask "What is the capital of France?"
     $first = ($out -split "`n")[0]
     if ($first -ceq "I can't find that in the course documents.") {
         "PASS — exact refusal on first line"
     } else {
         "FAIL — first line was: $first"
     }
     ```
   - **Expected:** `PASS — exact refusal on first line`.
   - **Bash equivalent:**
     ```bash
     test "$(python -m ask_the_course.ask 'What is the capital of France?' | head -n 1)" = "I can't find that in the course documents." && echo PASS || echo FAIL
     ```
   - **What it proves:** the model followed the system prompt and emitted
     the exact refusal string; the asker printed it verbatim without a
     prefix or apology.

5. **Asker — `--no-retrieval`.**
   - **Command (PowerShell):**
     ```powershell
     python -m ask_the_course.ask --no-retrieval "What is the late policy on assignments?"
     echo "exit=$LASTEXITCODE"
     ```
   - **Expected:** exit code `0`. Output is the model's answer followed
     by a one-line note that retrieval was disabled. **No chunk list** is
     printed, because no chunks were retrieved.
   - **What it proves:** the asker bypasses the embedding + retrieval
     step, calls the LLM with no course context, and the model answers
     from parametric knowledge. Visually compare to step 3 — the
     no-retrieval answer should miss the corpus (wrong date / wrong
     policy / wrong assignment name).

6. **`questions.json` — shape.**
   - **Command:**
     ```powershell
     python -c "import json; d=json.load(open('questions.json')); assert len(d)==5; k=[x['kind'] for x in d]; assert k.count('factual')==3 and 'multi-page' in k and 'out-of-scope' in k; print('shape ok')"
     ```
   - **Expected:** prints `shape ok` and exits `0`.
   - **What it proves:** the file has exactly five entries with the
     kinds the eval needs.

7. **`eval.py` — first run.**
   - **Command (PowerShell):**
     ```powershell
     python eval.py
     echo "exit=$LASTEXITCODE"
     (Get-Content CHECKS.md).Count
     ```
   - **Expected:** exit code `0`. `CHECKS.md` exists and contains
     exactly **10 dated runs** (5 questions × 2 modes), each formatted
     by `eval.py`'s per-run template. Each with-retrieval `factual` /
     `multi-page` run either matches `expected` or is flagged
     "non-conforming response" / "wrong answer." The `out-of-scope`
     with-retrieval run's first line equals the refusal string.
   - **What it proves:** spec behaviors #10 and #11 are satisfied —
     the eval ran end-to-end, the with-retrieval mode is grounded, and
     the no-retrieval mode visibly misses on factual questions.

8. **Stale-page run.**
   - **Command (PowerShell):**
     ```powershell
     python eval.py --stale
     ```
   - **Expected:** exit code `0`. `CHECKS.md` gains a new run whose
     chunk list contains at least one chunk from `weeks/01` **and** at
     least one chunk from `weeks/03`. The developer appends a one-line
     note in `CHECKS.md` describing a theoretical fix (last-modified
     metadata on chunks).
   - **What it proves:** spec behavior #12 — the eval exposes the
     conflict; the observation + theoretical fix are recorded.

9. **Final pass against spec behaviors.**
   - **Command:** no shell command; a manual checklist.
   - **Expected:** re-read `spec.md` behaviors #1–#12, tick each, and
     cite the `CHECKS.md` entry or file path that proves it. Anything
     not ticked loops back to the step that owns it.

## Subagents and parallel work

None. The work is small (one developer, one feature, one weekend of
files) and the pieces are tightly coupled: the asker depends on the
indexer's output format, the eval script depends on the asker's CLI
shape, and `questions.json` depends on knowing what's actually in the
corpus (which requires the indexer to have run). A subagent would add
coordination cost without saving wall-clock time. The closest candidate
for parallelism — drafting `questions.json` while writing the
indexer — is blocked on the indexer running first, so it isn't real
parallelism.

**Approved by:** Nadia Boudhaim Maguire
