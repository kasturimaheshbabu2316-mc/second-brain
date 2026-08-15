#!/usr/bin/env python3
"""Auto-link related wiki notes via embedding similarity."""

from __future__ import annotations

import argparse
import re
import sys

from lib.embeddings import (
    MODEL_NAME,
    EmbeddingError,
    cosine_similarity,
    embed_text,
    load_embeddings,
    prune_embeddings,
    save_embeddings,
)
from lib.models import WikiNote
from lib.storage import (
    content_hash,
    load_index,
    read_wiki_notes,
    save_index,
    write_wiki_note,
)

DEFAULT_THRESHOLD = 0.55
MAX_BODY_CHARS = 800
_WIKILINK_RE = re.compile(r"\[\[([a-zA-Z0-9_-]+)\]\]")
_RELATED_SECTION = "\n\n## Related\n"


def note_embed_text(note: WikiNote) -> str:
    """
    Build text for embedding: summary + tags + truncated body.

    Truncating body keeps long scraped pages from drowning the signal.
    """
    body = strip_related_section(note.body)
    body = _WIKILINK_RE.sub("", body).strip()
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS].rstrip() + "…"

    parts: list[str] = []
    if note.summary.strip():
        parts.append(note.summary.strip())
    if note.tags:
        parts.append("tags: " + ", ".join(note.tags))
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def strip_related_section(body: str) -> str:
    """Remove trailing auto-generated Related section if present."""
    match = re.search(r"\n## Related\n", body)
    if match:
        return body[: match.start()].rstrip()
    return body.rstrip()


def existing_wikilinks(body: str) -> set[str]:
    return set(_WIKILINK_RE.findall(body))


def related_wikilinks(body: str) -> set[str]:
    """Wikilinks only from the auto-generated Related section."""
    match = re.search(r"\n## Related\n(.*)$", body, re.DOTALL)
    if not match:
        return set()
    return set(_WIKILINK_RE.findall(match.group(1)))


def apply_links_to_note(note: WikiNote, link_ids: list[str]) -> WikiNote:
    """Merge link_ids into frontmatter and append a Related wikilink section."""
    merged_links = sorted(set(link_ids))
    base_body = strip_related_section(note.body)

    if merged_links:
        lines = "\n".join(f"- [[{lid}]]" for lid in merged_links)
        new_body = f"{base_body}{_RELATED_SECTION}{lines}\n"
    else:
        new_body = base_body + "\n"

    note.links = merged_links
    note.body = new_body
    return note


def _note_content_hash(note: WikiNote) -> str:
    return content_hash(note_embed_text(note))


def link_notes(
    *,
    threshold: float = DEFAULT_THRESHOLD,
    force: bool = False,
) -> int:
    """
    Embed wiki notes and write bidirectional similarity links.

    Returns:
        Number of note files written.
    """
    notes = read_wiki_notes()
    if not notes:
        print("Nothing to link — no wiki notes found. Run classify first.")
        return 0

    index = load_index()
    if index.embeddings_version != MODEL_NAME:
        print(
            f"Embedding model version changed "
            f"({index.embeddings_version} → {MODEL_NAME}); re-embedding all notes."
        )
        force = True
        index.embeddings_version = MODEL_NAME

    note_by_id = {n.id: n for n in notes}
    valid_ids = set(note_by_id)

    embeddings = {} if force else load_embeddings()
    embeddings = prune_embeddings(embeddings, valid_ids)
    wiki_embed_state = dict(index.wiki_embeddings or {})

    embedded = 0
    for note in notes:
        text = note_embed_text(note)
        if not text.strip():
            print(f"  Skipping empty note {note.id}")
            continue

        digest = _note_content_hash(note)
        prior = wiki_embed_state.get(note.id, {})
        needs_embed = (
            force
            or note.id not in embeddings
            or prior.get("content_hash") != digest
        )

        if needs_embed:
            print(f"Embedding {note.id}...")
            vector = embed_text(text)
            if not vector.any():
                print(f"  Warning: zero vector for {note.id}; skipping similarity")
                continue
            embeddings[note.id] = vector
            wiki_embed_state[note.id] = {"content_hash": digest}
            embedded += 1

    wiki_embed_state = {
        nid: meta for nid, meta in wiki_embed_state.items() if nid in valid_ids
    }

    adjacency: dict[str, set[str]] = {nid: set() for nid in embeddings}
    note_ids = list(embeddings.keys())
    for i, src in enumerate(note_ids):
        for tgt in note_ids[i + 1 :]:
            if src not in note_by_id or tgt not in note_by_id:
                continue
            score = cosine_similarity(embeddings[src], embeddings[tgt])
            if score >= threshold:
                adjacency[src].add(tgt)
                adjacency[tgt].add(src)

    save_embeddings(embeddings)

    linked_count = 0
    for note_id, note in note_by_id.items():
        new_links = sorted(
            lid for lid in adjacency.get(note_id, set()) if lid in note_by_id
        )
        old_links = sorted(note.links or [])
        body_links = related_wikilinks(note.body)
        needs_write = set(new_links) != set(old_links) or set(new_links) != body_links

        if needs_write:
            updated_note = apply_links_to_note(note, new_links)
            write_wiki_note(updated_note)
            linked_count += 1
            if new_links:
                print(
                    f"  Linked {note_id} ↔ {', '.join(new_links)} "
                    f"({len(new_links)} link(s))"
                )
            elif old_links:
                print(f"  Cleared links for {note_id}")

    index.wiki_embeddings = wiki_embed_state
    index.embeddings_version = MODEL_NAME
    save_index(index)

    print(
        f"\nLinking complete. Threshold={threshold:.2f}. "
        f"Embedded {embedded} note(s); wrote {linked_count} note file(s)."
    )
    return linked_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Auto-link related wiki notes via embeddings",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Cosine similarity threshold (default {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed all notes even if content hash matches",
    )
    args = parser.parse_args(argv)

    if not 0.0 < args.threshold <= 1.0:
        print("Error: threshold must be between 0 and 1", file=sys.stderr)
        return 2

    try:
        link_notes(threshold=args.threshold, force=args.force)
    except EmbeddingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
