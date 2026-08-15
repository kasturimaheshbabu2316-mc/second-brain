#!/usr/bin/env python3
"""Capture notes, links, and files into raw/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from lib.models import CaptureMeta, CaptureResult, CaptureSource
from lib.storage import (
    content_hash,
    generate_capture_id,
    read_raw_captures,
    utc_now_iso,
    write_raw_capture,
)


class CaptureError(Exception):
    """Raised when capture input is invalid."""


def _existing_hashes() -> set[str]:
    hashes: set[str] = set()
    for capture in read_raw_captures():
        if capture.meta.content_hash:
            hashes.add(capture.meta.content_hash)
    return hashes


def _warn_duplicate(content: bytes | str) -> None:
    digest = content_hash(content)
    if digest in _existing_hashes():
        print(f"Warning: duplicate content detected ({digest})", file=sys.stderr)


def _make_meta(
    capture_type: str,
    source: CaptureSource,
    *,
    original_filename: str | None = None,
) -> CaptureMeta:
    short_id, _folder_id = generate_capture_id()
    return CaptureMeta(
        id=short_id,
        timestamp=utc_now_iso(),
        type=capture_type,  # type: ignore[arg-type]
        source=source,
        original_filename=original_filename,
    )


def _result_from_capture(meta: CaptureMeta, capture_dir: Path) -> CaptureResult:
    return CaptureResult(
        id=meta.folder_id,
        path=str(capture_dir),
        type=meta.type,
    )


def _print_confirmation(folder_id: str) -> None:
    print(f"Captured → raw/{folder_id}")


def _is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def capture_note(
    text: str,
    *,
    source: CaptureSource = "cli",
) -> CaptureResult:
    """Capture plain text or markdown as a note."""
    if not text or not text.strip():
        raise CaptureError("Note text cannot be empty.")

    content = text.strip()
    _warn_duplicate(content)
    meta = _make_meta("note", source)
    capture_dir = write_raw_capture(meta, content)
    _print_confirmation(meta.folder_id)
    return _result_from_capture(meta, capture_dir)


def capture_link(
    url: str,
    notes: str = "",
    *,
    source: CaptureSource = "cli",
) -> CaptureResult:
    """Capture a URL with optional notes."""
    url = url.strip()
    if not url:
        raise CaptureError("URL cannot be empty.")
    if not _is_valid_url(url):
        raise CaptureError(f"Invalid URL (use http:// or https://): {url}")

    content = url
    if notes.strip():
        content = f"{url}\n\n{notes.strip()}"

    _warn_duplicate(content)
    meta = _make_meta("link", source)
    capture_dir = write_raw_capture(meta, content)
    _print_confirmation(meta.folder_id)
    return _result_from_capture(meta, capture_dir)


def capture_file(
    path: str | Path,
    *,
    source: CaptureSource = "path",
) -> CaptureResult:
    """Capture a local file by copying it into raw/."""
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        raise CaptureError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise CaptureError(f"Not a file: {file_path}")

    content = file_path.read_bytes()
    _warn_duplicate(content)
    meta = _make_meta("file", source, original_filename=file_path.name)
    capture_dir = write_raw_capture(meta, content)
    _print_confirmation(meta.folder_id)
    return _result_from_capture(meta, capture_dir)


def capture_interactive() -> CaptureResult:
    """Read a multi-line note from stdin until EOF."""
    if not sys.stdin.isatty():
        text = sys.stdin.read()
        return capture_note(text, source="stdin")

    print("Enter note text (Ctrl+D / Ctrl+Z to finish):")
    lines: list[str] = []
    try:
        while True:
            lines.append(input())
    except EOFError:
        pass

    return capture_note("\n".join(lines), source="stdin")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture notes, links, and files into SecondSelf raw/",
    )
    subparsers = parser.add_subparsers(dest="command")

    note_parser = subparsers.add_parser("note", help="Capture a text note")
    note_parser.add_argument("text", help="Note content")

    link_parser = subparsers.add_parser("link", help="Capture a URL")
    link_parser.add_argument("url", help="URL to capture")
    link_parser.add_argument(
        "notes",
        nargs="?",
        default="",
        help="Optional notes about the link",
    )

    file_parser = subparsers.add_parser("file", help="Capture a local file")
    file_parser.add_argument("path", help="Path to the file")

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "note":
            capture_note(args.text)
        elif args.command == "link":
            capture_link(args.url, args.notes)
        elif args.command == "file":
            capture_file(args.path)
        elif not argv:
            capture_interactive()
        else:
            parser.print_help()
            return 2
    except CaptureError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
