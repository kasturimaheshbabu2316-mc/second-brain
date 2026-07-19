import os
import sys
import json
import uuid
import argparse
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import urllib.parse

# Configurations
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB size limit for text extraction
TIMEOUT_SECONDS = 8
RAW_DIR = "raw"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Supported text extensions
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".json", ".csv", ".tsv",
    ".html", ".xml", ".css", ".yaml", ".yml", ".ini", ".conf", ".sh", ".bat"
}

def sanitize_filename(name: str) -> str:
    """Sanitize the string to make it safe for filenames."""
    return "".join(c for c in name if c.isalnum() or c in "._- ").strip()

def save_raw_capture(capture_type: str, content: str, source: str, metadata: dict):
    """Saves the captured content into a unified JSON format under the raw/ folder."""
    os.makedirs(RAW_DIR, exist_ok=True)
    
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    capture_id = str(uuid.uuid4())
    short_id = capture_id.hex[:4] if hasattr(capture_id, "hex") else capture_id[:4]
    
    payload = {
        "id": capture_id,
        "timestamp": now.isoformat(),
        "type": capture_type,
        "source": source,
        "content": content,
        "metadata": metadata
    }
    
    filename = f"capture_{timestamp_str}_{short_id}.json"
    filepath = os.path.join(RAW_DIR, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    
    print(f"Successfully captured {capture_type} -> {filepath}")
    return filepath

def process_note(text: str):
    """Processes a simple raw note."""
    if not text.strip():
        print("Error: Note content cannot be empty.", file=sys.stderr)
        return
    save_raw_capture(
        capture_type="note",
        content=text.strip(),
        source="cli-note",
        metadata={}
    )

def process_link(url: str):
    """Fetches a URL, extracts readable text, and saves it."""
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme not in ("http", "https"):
        print(f"Error: Invalid URL scheme '{parsed_url.scheme}'. Only HTTP and HTTPS are supported.", file=sys.stderr)
        return
        
    print(f"Fetching link: {url}...")
    headers = {"User-Agent": USER_AGENT}
    metadata = {"url": url}
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        
        # Try to detect encoding or fallback to response.apparent_encoding
        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Extract title
        title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled Link"
        metadata["title"] = title
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
            script_or_style.decompose()
            
        # Extract plain text content
        text = soup.get_text(separator="\n")
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = "\n".join(chunk for chunk in chunks if chunk)
        
        if not clean_text.strip():
            content = f"Empty or unreadable content. Title: {title}"
        else:
            content = f"Title: {title}\n\nContent:\n{clean_text}"
            
    except Exception as e:
        print(f"Warning: Failed to fetch full page content ({e}). Logging link metadata only.", file=sys.stderr)
        content = f"Failed to fetch content for {url}. Error: {str(e)}"
        metadata["error"] = str(e)

    save_raw_capture(
        capture_type="link",
        content=content,
        source="cli-link",
        metadata=metadata
    )

def process_file(filepath: str):
    """Processes a local file, performing text extraction or logging metadata depending on type/size."""
    if not os.path.exists(filepath):
        print(f"Error: File does not exist: {filepath}", file=sys.stderr)
        return
    if os.path.isdir(filepath):
        print(f"Error: Path is a directory, not a file: {filepath}", file=sys.stderr)
        return
        
    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    ext = os.path.splitext(filename)[1].lower()
    
    metadata = {
        "original_filename": filename,
        "file_size_bytes": file_size,
        "extension": ext,
        "absolute_path": os.path.abspath(filepath)
    }
    
    # Check file size limit
    if file_size > MAX_FILE_SIZE_BYTES:
        print(f"Warning: File size ({file_size} bytes) exceeds limit ({MAX_FILE_SIZE_BYTES} bytes). Extracting metadata only.", file=sys.stderr)
        metadata["status"] = "exceeded_size_limit"
        content = f"File '{filename}' exceeds size limit. Metadata-only capture."
        save_raw_capture("file", content, "cli-file", metadata)
        return

    # Check if text file type
    if ext not in TEXT_EXTENSIONS:
        # Treat as binary/unsupported type
        print(f"Warning: Extension '{ext}' is not in the text extraction whitelist. Extracting metadata only.", file=sys.stderr)
        metadata["status"] = "binary_unsupported"
        content = f"Binary or unsupported file type '{filename}'. Metadata-only capture."
        save_raw_capture("file", content, "cli-file", metadata)
        return
        
    # Attempt to read text content
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            metadata["status"] = "extracted"
    except UnicodeDecodeError:
        # Retry with fallback encoding
        try:
            print(f"UTF-8 decode failed for {filename}. Retrying with Latin-1 fallback.", file=sys.stderr)
            with open(filepath, "r", encoding="latin-1") as f:
                content = f.read()
                metadata["status"] = "extracted_latin1"
        except Exception as e:
            metadata["status"] = "read_failed"
            metadata["error"] = str(e)
            content = f"Failed to read file content for '{filename}' due to encoding errors."
    except Exception as e:
        metadata["status"] = "read_failed"
        metadata["error"] = str(e)
        content = f"Failed to read file content for '{filename}'. Error: {str(e)}"
        
    save_raw_capture(
        capture_type="file",
        content=content,
        source="cli-file",
        metadata=metadata
    )

def main():
    parser = argparse.ArgumentParser(description="SecondSelf Capture CLI - Phase 1")
    parser.add_argument("--note", type=str, help="Inline note/thought text to capture")
    parser.add_argument("--link", type=str, help="Web URL to scrape and capture")
    parser.add_argument("--file", type=str, help="Local file path to read and capture")
    
    args = parser.parse_args()
    
    if not (args.note or args.link or args.file):
        parser.print_help()
        sys.exit(1)
        
    if args.note:
        process_note(args.note)
    if args.link:
        process_link(args.link)
    if args.file:
        process_file(args.file)

if __name__ == "__main__":
    main()
