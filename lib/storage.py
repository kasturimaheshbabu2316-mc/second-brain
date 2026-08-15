"""Filesystem helpers for SecondSelf."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from lib.models import (
    PARA_CATEGORIES,
    CaptureMeta,
    IndexState,
    RawCapture,
    WikiNote,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "raw"
WIKI_DIR = PROJECT_ROOT / "wiki"
DATA_DIR = PROJECT_ROOT / "data"
INDEX_PATH = DATA_DIR / "index.json"
GRAPH_PATH = DATA_DIR / "graph.json"

CONTENT_FILENAMES = {
    "note": "content.md",
    "link": "content.txt",
}


def ensure_dirs() -> None:
    """Create required project directories if missing."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for category in PARA_CATEGORIES:
        (WIKI_DIR / category).mkdir(parents=True, exist_ok=True)


def generate_capture_id() -> tuple[str, str]:
    """
    Generate a capture ID.

    Returns:
        (short_id, folder_id) where folder_id is {YYYY-MM-DD}_{uuid8}.
    """
    short_id = uuid.uuid4().hex[:8]
    date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder_id = f"{date_part}_{short_id}"
    return short_id, folder_id


def content_hash(data: bytes | str) -> str:
    """Return SHA-256 hash prefixed with 'sha256:'."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    return f"sha256:{digest}"


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _content_filename(capture_type: str, original_filename: str | None) -> str:
    if capture_type == "note":
        return "content.md"
    if capture_type == "link":
        return "content.txt"
    if original_filename:
        suffix = Path(original_filename).suffix or ".bin"
        return f"content{suffix}"
    return "content.bin"


def write_raw_capture(meta: CaptureMeta, content: bytes | str) -> Path:
    """
    Create raw/{folder_id}/ with meta.json and content file.

    Returns:
        Path to the capture directory.
    """
    ensure_dirs()

    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content

    if meta.content_hash is None:
        meta.content_hash = content_hash(content_bytes)

    folder_id = meta.folder_id
    capture_dir = RAW_DIR / folder_id
    capture_dir.mkdir(parents=True, exist_ok=True)

    content_name = _content_filename(meta.type, meta.original_filename)
    content_path = capture_dir / content_name
    if isinstance(content, str):
        content_path.write_text(content, encoding="utf-8")
    else:
        content_path.write_bytes(content_bytes)

    meta_path = capture_dir / "meta.json"
    meta_dict = {
        "id": meta.id,
        "timestamp": meta.timestamp,
        "type": meta.type,
        "source": meta.source,
        "original_filename": meta.original_filename,
        "content_hash": meta.content_hash,
    }
    meta_path.write_text(json.dumps(meta_dict, indent=2) + "\n", encoding="utf-8")

    return capture_dir


def _load_capture_meta(meta_path: Path) -> CaptureMeta:
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    return CaptureMeta(
        id=data["id"],
        timestamp=data["timestamp"],
        type=data["type"],
        source=data["source"],
        original_filename=data.get("original_filename"),
        content_hash=data.get("content_hash"),
    )


def _find_content_file(capture_dir: Path) -> Path | None:
    for path in sorted(capture_dir.iterdir()):
        if path.name == "meta.json":
            continue
        if path.name.startswith("content."):
            return path
    return None


def _parse_raw_capture(capture_dir: Path) -> RawCapture | None:
    meta_path = capture_dir / "meta.json"
    if not meta_path.is_file():
        return None

    meta = _load_capture_meta(meta_path)
    content_path = _find_content_file(capture_dir)
    return RawCapture(
        folder_id=capture_dir.name,
        meta=meta,
        path=str(capture_dir),
        content_path=str(content_path) if content_path else None,
    )


def read_raw_captures(*, unprocessed_only: bool = False) -> list[RawCapture]:
    """
    List raw captures from raw/.

    Args:
        unprocessed_only: If True, exclude items already in index.json.
    """
    ensure_dirs()
    index = load_index() if unprocessed_only else None
    captures: list[RawCapture] = []

    if not RAW_DIR.is_dir():
        return captures

    for capture_dir in sorted(RAW_DIR.iterdir()):
        if not capture_dir.is_dir():
            continue
        raw = _parse_raw_capture(capture_dir)
        if raw is None:
            continue
        if unprocessed_only and index is not None:
            if raw.folder_id in index.raw_processed:
                continue
        captures.append(raw)

    return captures


def load_index() -> IndexState:
    """Load data/index.json, initializing defaults if missing or corrupt."""
    ensure_dirs()
    if not INDEX_PATH.is_file():
        state = IndexState()
        save_index(state)
        return state

    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("index.json root must be an object")
        return IndexState.from_dict(data)
    except (json.JSONDecodeError, ValueError, OSError):
        return IndexState()


def save_index(state: IndexState) -> None:
    """Atomically write data/index.json."""
    ensure_dirs()
    tmp_path = INDEX_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(state.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(INDEX_PATH)


def write_wiki_note(note: WikiNote) -> Path:
    """Write wiki/{para}/{id}.md with YAML frontmatter and body."""
    ensure_dirs()

    if note.para not in PARA_CATEGORIES:
        raise ValueError(f"Invalid PARA category: {note.para}")

    note_path = WIKI_DIR / note.para / f"{note.id}.md"
    frontmatter = {
        "id": note.id,
        "raw_id": note.raw_id,
        "para": note.para,
        "tags": note.tags,
        "summary": note.summary,
        "created": note.created,
        "links": note.links,
    }
    yaml_block = yaml.safe_dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    content = f"---\n{yaml_block}\n---\n\n{note.body.rstrip()}\n"
    note_path.write_text(content, encoding="utf-8")
    return note_path


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_wiki_note(note_path: Path) -> WikiNote | None:
    text = note_path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None

    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).lstrip("\n")

    para = frontmatter.get("para", "Resources")
    if para not in PARA_CATEGORIES:
        para = "Resources"

    return WikiNote(
        id=str(frontmatter.get("id", note_path.stem)),
        raw_id=str(frontmatter.get("raw_id", "")),
        para=para,
        tags=list(frontmatter.get("tags") or []),
        summary=str(frontmatter.get("summary", "")),
        created=str(frontmatter.get("created", "")),
        links=[str(link_id) for link_id in (frontmatter.get("links") or [])],
        body=body,
        path=str(note_path),
    )


def read_wiki_notes() -> list[WikiNote]:
    """Parse all wiki/**/*.md notes."""
    ensure_dirs()
    notes: list[WikiNote] = []

    for category in PARA_CATEGORIES:
        category_dir = WIKI_DIR / category
        if not category_dir.is_dir():
            continue
        for note_path in sorted(category_dir.glob("*.md")):
            note = _parse_wiki_note(note_path)
            if note is not None:
                notes.append(note)

    return notes


def write_graph(graph: dict) -> Path:
    """Atomically write data/graph.json."""
    ensure_dirs()
    tmp_path = GRAPH_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(GRAPH_PATH)
    return GRAPH_PATH


def load_graph() -> dict | None:
    """Load data/graph.json, or None if missing/corrupt."""
    if not GRAPH_PATH.is_file():
        return None
    try:
        data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None
