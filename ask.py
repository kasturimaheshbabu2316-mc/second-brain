#!/usr/bin/env python3
"""Ask questions against the wiki via embedding retrieval + LLM synthesis."""

from __future__ import annotations

import argparse
import re
import sys

from lib.embeddings import EmbeddingError, cosine_similarity, embed_text, load_embeddings
from lib.llm import LLMError, synthesize_answer
from lib.models import AskResult, AskSource, WikiNote
from lib.storage import read_wiki_notes

DEFAULT_TOP_K = 5
MIN_RELEVANCE = 0.3
# ~6000 tokens of English ≈ 4 chars/token
MAX_CONTEXT_CHARS = 24_000
MAX_NOTE_CHARS = 4_000

NO_NOTES_MSG = "I don't have notes about that."
NO_INDEX_MSG = "No notes indexed yet. Run the pipeline first."
EMPTY_QUESTION_MSG = "Please enter a question."

_RELATED_RE = re.compile(r"\n## Related\n.*$", re.DOTALL)


def _strip_related(body: str) -> str:
    return _RELATED_RE.sub("", body or "").rstrip()


def format_note_chunk(note: WikiNote, max_chars: int) -> str:
    """Format one note for the RAG context window."""
    summary = (note.summary or "").strip()
    tags = ", ".join(note.tags or [])
    header_parts = [f"[{note.id}] ({note.para})"]
    if summary:
        header_parts.append(f"Summary: {summary}")
    if tags:
        header_parts.append(f"Tags: {tags}")
    header = "\n".join(header_parts) + "\nContent:\n"

    body = _strip_related(note.body)
    budget = max_chars - len(header)
    if budget < 80:
        return (header + body)[:max_chars].rstrip() + "…"

    if len(body) > budget:
        body = body[:budget].rstrip() + "\n[... truncated ...]"
    return header + body


def build_context(notes: list[WikiNote], *, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Pack notes (already relevance-ordered) into a bounded context string."""
    parts: list[str] = []
    used = 0
    for note in notes:
        room = max_chars - used
        if room < 200:
            break
        chunk = format_note_chunk(note, min(MAX_NOTE_CHARS, room))
        if used + len(chunk) > max_chars:
            room = max_chars - used
            if room < 200:
                break
            chunk = format_note_chunk(note, room)
        parts.append(chunk)
        used += len(chunk) + 2
    return "\n\n".join(parts)


def retrieve(
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_RELEVANCE,
) -> list[tuple[WikiNote, float]]:
    """
    Embed the question and return top-K wiki notes above min_score.

    Skips embedding IDs whose wiki files are missing.
    """
    embeddings = load_embeddings()
    if not embeddings:
        return []

    notes = {n.id: n for n in read_wiki_notes()}
    query_vec = embed_text(question)

    scored: list[tuple[WikiNote, float]] = []
    for note_id, vector in embeddings.items():
        note = notes.get(note_id)
        if note is None:
            continue
        score = cosine_similarity(query_vec, vector)
        if score >= min_score:
            scored.append((note, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[: max(1, top_k)]


def ask(question: str, top_k: int = DEFAULT_TOP_K) -> AskResult:
    """
    Answer a question from the personal wiki (RAG).

    Returns AskResult with answer text and ranked sources.
    """
    cleaned = (question or "").strip()
    if not cleaned:
        return AskResult(answer=EMPTY_QUESTION_MSG, sources=[])

    embeddings = load_embeddings()
    if not embeddings:
        return AskResult(answer=NO_INDEX_MSG, sources=[])

    hits = retrieve(cleaned, top_k=top_k, min_score=MIN_RELEVANCE)
    if not hits:
        return AskResult(answer=NO_NOTES_MSG, sources=[])

    sources = [
        AskSource(
            id=note.id,
            summary=note.summary,
            relevance_score=round(score, 4),
            para=note.para,
        )
        for note, score in hits
    ]

    context = build_context([note for note, _ in hits])
    if not context.strip():
        return AskResult(answer=NO_NOTES_MSG, sources=[])

    answer = synthesize_answer(context, cleaned)
    return AskResult(answer=answer, sources=sources)


def _print_result(result: AskResult) -> None:
    print(result.answer)
    if result.sources:
        print("\nSources:")
        for src in result.sources:
            print(
                f"  [{src.id}] ({src.para}) "
                f"score={src.relevance_score:.3f} — {src.summary}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ask a question against your SecondSelf wiki",
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="Question in plain English",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of notes to retrieve (default {DEFAULT_TOP_K})",
    )
    args = parser.parse_args(argv)

    question = args.question
    if question is None:
        try:
            question = input("Ask your brain: ").strip()
        except EOFError:
            question = ""

    if args.top_k < 1:
        print("Error: --top-k must be >= 1", file=sys.stderr)
        return 2

    try:
        result = ask(question, top_k=args.top_k)
    except EmbeddingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except LLMError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
