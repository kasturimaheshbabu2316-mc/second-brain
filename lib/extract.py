"""Text extraction helpers for raw captures."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Use macOS/system trust store — required on some Python builds (e.g. 3.14)
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from lib.models import RawCapture

FETCH_TIMEOUT_SECONDS = 30
MAX_FETCH_CHARS = 50_000
USER_AGENT = "SecondSelf/0.1 (+local knowledge capture)"

_URL_RE = re.compile(r"^https?://\S+", re.IGNORECASE)

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".markdown",
    ".rst",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".htm",
    ".xml",
    ".log",
}


def extract_text(capture: RawCapture) -> str:
    """
    Extract classify-ready text from a raw capture.

    Falls back gracefully when fetch/PDF extraction fails.
    """
    capture_type = capture.meta.type
    if capture_type == "note":
        return _extract_note(capture)
    if capture_type == "link":
        return _extract_link(capture)
    if capture_type == "file":
        return _extract_file(capture)
    return _metadata_fallback(capture)


def _read_content_text(capture: RawCapture) -> str:
    if not capture.content_path:
        return ""
    path = Path(capture.content_path)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    except OSError:
        return ""


def _extract_note(capture: RawCapture) -> str:
    text = _read_content_text(capture).strip()
    if text:
        return text
    return _metadata_fallback(capture)


def _parse_link_content(content: str) -> tuple[str, str]:
    """Return (url, user_notes) from link content.txt."""
    lines = content.strip().splitlines()
    if not lines:
        return "", ""
    first = lines[0].strip()
    url = first if _URL_RE.match(first) else ""
    if url:
        notes = "\n".join(lines[1:]).strip()
    else:
        # No URL on first line — treat whole file as notes; try to find a URL
        notes = content.strip()
        match = _URL_RE.search(content)
        url = match.group(0) if match else ""
    return url, notes


def _extract_link(capture: RawCapture) -> str:
    content = _read_content_text(capture)
    url, notes = _parse_link_content(content)

    parts: list[str] = []
    if url:
        parts.append(f"URL: {url}")
        fetched = _fetch_url_text(url)
        if fetched:
            parts.append(fetched)
    if notes:
        parts.append(f"User notes:\n{notes}")

    text = "\n\n".join(parts).strip()
    if text:
        return text
    return _metadata_fallback(capture)


def _fetch_url_text(url: str) -> str:
    """Fetch URL and strip HTML; return empty string on failure."""
    try:
        response = requests.get(
            url,
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"  Warning: URL fetch failed ({url}): {exc}", file=sys.stderr)
        return ""

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "html" not in content_type and "text/plain" not in content_type:
        # Binary / PDF / etc. — don't parse as HTML
        path = urlparse(url).path
        name = Path(path).name or url
        return f"[Non-HTML resource: {name}]"

    if "text/plain" in content_type:
        return response.text[:MAX_FETCH_CHARS].strip()

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()

        title = (soup.title.string or "").strip() if soup.title else ""
        meta_desc = ""
        meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta and meta.get("content"):
            meta_desc = str(meta["content"]).strip()

        body_text = soup.get_text(separator="\n", strip=True)
        body_text = re.sub(r"\n{3,}", "\n\n", body_text)

        chunks: list[str] = []
        if title:
            chunks.append(f"Title: {title}")
        if meta_desc:
            chunks.append(f"Description: {meta_desc}")
        if body_text:
            chunks.append(body_text[:MAX_FETCH_CHARS])

        result = "\n\n".join(chunks).strip()
        # SPA with empty body — title/meta alone is still useful
        return result
    except Exception as exc:  # noqa: BLE001 — defensive HTML parse
        print(f"  Warning: HTML parse failed ({url}): {exc}", file=sys.stderr)
        return ""


def _extract_file(capture: RawCapture) -> str:
    content_path = Path(capture.content_path) if capture.content_path else None
    original = capture.meta.original_filename or (
        content_path.name if content_path else "unknown"
    )
    suffix = Path(original).suffix.lower()
    if content_path is not None:
        suffix = content_path.suffix.lower() or suffix

    if content_path and content_path.is_file():
        if suffix == ".pdf":
            text = _extract_pdf(content_path, original)
            if text:
                return text
            return (
                f"Filename: {original}\n"
                f"[PDF had no extractable text — may need OCR]\ntags hint: needs-ocr"
            )

        if suffix in TEXT_EXTENSIONS or _looks_like_text(content_path):
            text = _read_content_text(capture).strip()
            if text:
                return f"Filename: {original}\n\n{text}"

    return (
        f"Filename: {original}\n"
        f"Type: file\n"
        f"Captured: {capture.meta.timestamp}"
    )


def _extract_pdf(path: Path, original_filename: str) -> str:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            print(
                f"  Warning: PDF is password-protected ({original_filename})",
                file=sys.stderr,
            )
            return ""

        pages: list[str] = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                page_text = ""
            if page_text.strip():
                pages.append(page_text.strip())

        text = "\n\n".join(pages).strip()
        if not text:
            print(
                f"  Warning: PDF has no text layer ({original_filename})",
                file=sys.stderr,
            )
            return ""
        return f"Filename: {original_filename}\n\n{text}"
    except Exception as exc:  # noqa: BLE001
        print(
            f"  Warning: PDF extract failed ({original_filename}): {exc}",
            file=sys.stderr,
        )
        return ""


def _looks_like_text(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return False
    if not sample:
        return True
    # Heuristic: mostly printable / whitespace
    text_chars = sum(1 for b in sample if 9 <= b <= 13 or 32 <= b <= 126 or b >= 128)
    return (text_chars / len(sample)) > 0.85


def _metadata_fallback(capture: RawCapture) -> str:
    name = capture.meta.original_filename or capture.folder_id
    return (
        f"Capture id: {capture.folder_id}\n"
        f"Type: {capture.meta.type}\n"
        f"Filename: {name}\n"
        f"Captured: {capture.meta.timestamp}"
    )
