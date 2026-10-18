# Intent: ask-the-course

## Goal
A command-line tool that answers a question about CPSC 415 using only the
course's Markdown pages, cites the pages it used, and replies with exactly
`I can't find that in the course documents.` when those pages don't contain
the answer.

## Who it is for
Runs locally on the developer's machine (and possibly by the professor when
grading). It is not deployed, not a web app, and not for general student use.
Today, finding an answer about the course means opening the right file
by hand and skimming.

## Constraints
- The corpus is fixed and read in place from `../ai-integration-course/`:
  `syllabus.md`, `assignments/`, and `weeks/01` through `weeks/03`.
  `weeks/04` is excluded. Pages are never copied into this repo.
- The tool must answer strictly from this corpus. If the answer is not
  present, it must reply with exactly `I can't find that in the course documents.`
  — no paraphrasing, no guessing.
- Every answer must print the retrieved chunks below the answer, each with
  its similarity score and source in the form `[file_path > section heading]`,
  e.g. `weeks/03/lab.md > 4. The second model`.
- The LLM is instructed via system prompt to cite the pages it used inline
  in the answer itself.
- The tool is single-shot: one question in, one answer out, then exit.
- A separate batch evaluation script reads five test questions from a
  `questions.json` file.
- A "no retrieval" mode must exist so the same evaluation can be run twice
  (with and without retrieval) and the two runs compared in `CHECKS.md`.
- A RAG framework (e.g. LangChain, LangChain4j, Spring AI) is allowed, and
  any library used must be named with its reason in `spec.md`.

## Not in scope
- Programmatic resolution of stale or conflicting pages. The "stale page"
  scenario is an observation exercise, not a feature: the tool retrieves
  both an outdated `weeks/01` page and the current `weeks/03` page, the
  LLM answers however it likes, and the developer records what happened
  in `CHECKS.md` along with one theoretical fix (e.g. adding last-modified
  metadata to chunk metadata). No code change is required.
- Conversation memory across questions.
- A web UI, multi-user service, or any deployment.
- Training or fine-tuning a model.
- Course content outside `syllabus.md`, `assignments/`, and `weeks/01`–`weeks/03`.

## Success looks like
1. A five-question evaluation, recorded in `CHECKS.md`, shows the tool:
   - answering three factual questions correctly,
   - answering one multi-page policy question correctly with citations
     spanning multiple pages,
   - replying with exactly `I can't find that in the course documents.` to
     one out-of-scope question.
   Every answer in that run (including the refusal) prints the retrieved
   chunks and their similarity scores below the answer.
2. The same five questions are run a second time without retrieval and
   recorded in `CHECKS.md`. That run fails the course-specific factual
   questions, demonstrating that retrieval is what makes the system work.
3. A "stale page" eval run is included in `CHECKS.md`: a question where an
   outdated `weeks/01` page and a current `weeks/03` page both get
   retrieved. The notes record what the LLM answered, which chunks it
   cited, and one theoretical way a RAG system could prefer the newer
   page. No implementation is expected.

## Open questions
- Language and library choice (e.g. Python + a RAG framework, or Java +
  Spring AI). To be settled in the spec, with reasons for each dependency.
- Which model and how it is accessed (hosted API or local). To be settled
  in the spec, with a cheap-versus-frontier comparison.
- Chunking strategy (by section, by token count, by header). To be settled
  in the spec.
- Exact shape of `questions.json` (array of strings, or objects with id
  and text). To be settled in the spec.

**Approved by:** Nadia Boudhaim Maguire
