#!/usr/bin/env python3
"""Classify unprocessed raw captures into PARA wiki notes."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from lib.extract import extract_text
from lib.llm import LLMError, classify_content
from lib.models import PARA_CATEGORIES, RawCapture, WikiNote
from lib.storage import (
    WIKI_DIR,
    load_index,
    read_raw_captures,
    read_wiki_notes,
    save_index,
    utc_now_iso,
    write_wiki_note,
)

# Brief pause between Groq calls to reduce rate-limit hits
BATCH_PAUSE_SECONDS = 0.5


def _existing_links_by_id() -> dict[str, list[str]]:
    """Preserve links[] when re-classifying an existing wiki note."""
    return {note.id: list(note.links) for note in read_wiki_notes()}


def _should_process(capture: RawCapture, index_raw: dict) -> bool:
    """True if never processed or content hash changed."""
    entry = index_raw.get(capture.folder_id)
    if entry is None:
        return True
    stored_hash = entry.get("content_hash")
    current_hash = capture.meta.content_hash
    return bool(current_hash and stored_hash and current_hash != stored_hash)


def _clean_body(text: str) -> str:
    """Normalize whitespace for wiki body storage."""
    return text.strip() + "\n" if text.strip() else ""


def _remove_existing_wiki_notes(note_id: str, *, keep_para: str | None = None) -> None:
    """Delete prior wiki files for this id (handles PARA moves on re-classify)."""
    for category in PARA_CATEGORIES:
        if keep_para and category == keep_para:
            continue
        path = WIKI_DIR / category / f"{note_id}.md"
        if path.is_file():
            path.unlink()


def classify_capture(
    capture: RawCapture,
    *,
    existing_links: dict[str, list[str]] | None = None,
) -> WikiNote:
    """Extract text, classify with LLM, and write a wiki note."""
    text = extract_text(capture)
    result = classify_content(text)

    note_id = capture.meta.id
    links = list((existing_links or {}).get(note_id, []))

    note = WikiNote(
        id=note_id,
        raw_id=capture.folder_id,
        para=result["para"],
        tags=result["tags"],
        summary=result["summary"],
        created=capture.meta.timestamp,
        links=links,
        body=_clean_body(text),
    )
    _remove_existing_wiki_notes(note_id, keep_para=note.para)
    path = write_wiki_note(note)
    note.path = str(path)
    return note


def classify_all(*, force: bool = False) -> int:
    """
    Classify all unprocessed (or hash-changed) raw captures.

    Returns:
        Number of notes classified.
    """
    index = load_index()
    captures = read_raw_captures()

    to_process: list[RawCapture] = []
    for capture in captures:
        if force or _should_process(capture, index.raw_processed):
            to_process.append(capture)

    if not to_process:
        print("Nothing to classify.")
        return 0

    existing_links = _existing_links_by_id()
    classified = 0

    for i, capture in enumerate(to_process):
        print(f"Classifying {capture.folder_id} ({capture.meta.type})...")
        try:
            note = classify_capture(capture, existing_links=existing_links)
        except LLMError as exc:
            print(f"  Error: {exc}", file=sys.stderr)
            # Auth failures should abort the batch
            if "GROQ_API_KEY" in str(exc) or "Invalid or expired" in str(exc):
                raise
            print("  Skipping — continuing batch.", file=sys.stderr)
            continue
        except OSError as exc:
            print(f"  Error writing wiki note: {exc}", file=sys.stderr)
            continue

        index.raw_processed[capture.folder_id] = {
            "wiki_id": note.id,
            "classified_at": utc_now_iso(),
            "content_hash": capture.meta.content_hash,
            "para": note.para,
            "path": str(Path(note.path).relative_to(WIKI_DIR.parent))
            if note.path
            else "",
        }
        save_index(index)
        classified += 1
        print(
            f"  → wiki/{note.para}/{note.id}.md"
            f"  [{', '.join(note.tags) or 'no tags'}]"
            f"  {note.summary[:80]}"
        )

        if i < len(to_process) - 1:
            time.sleep(BATCH_PAUSE_SECONDS)

    print(f"\nClassified {classified} capture(s).")
    return classified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify raw captures into PARA wiki notes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-classify all raw captures, even if already processed",
    )
    args = parser.parse_args(argv)

    try:
        classify_all(force=args.force)
    except LLMError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
