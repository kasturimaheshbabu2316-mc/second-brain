import os
import sys
import json
import re
import requests
import argparse
import time
from datetime import datetime, timezone

# Configurations
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:0.5b"
WIKI_DIR = "wiki"
RAW_DIR = "raw"
CATEGORIES = ["Projects", "Areas", "Resources", "Archives"]

SYSTEM_PROMPT = """You are "The Librarian", the auto-classification engine for the SecondSelf AI Second Brain.
Analyze the provided content and classify it into one of the four PARA categories:
1. Projects: Active endeavors with a specific goal and deadline (e.g., plans, active tasks, project draft docs, build logs).
2. Areas: Long-term responsibilities requiring ongoing standard of activity (e.g., health, finance, career, parenting, fitness).
3. Resources: Topics of interest, reference materials, guides, cheat sheets, or useful bookmarks/links (e.g., research, cooking recipes, programming cheat sheets).
4. Archives: Inactive items from the other three categories (e.g., completed projects, cold notes, completed checklists).

You must respond with a JSON object containing:
{
  "category": "Projects | Areas | Resources | Archives",
  "tags": ["tag1", "tag2"],
  "summary": "a single-sentence, concise summary of the content",
  "clean_title": "A short, descriptive, safe filename title (use only alphanumeric characters, spaces, hyphens, and underscores; do NOT include file extensions)"
}
Only output the JSON object. Do not include any other text."""

def sanitize_title(title: str) -> str:
    """Removes characters that are invalid in Windows/Linux filenames."""
    title = re.sub(r'[\\/*?:"<>|]', "", title)
    title = title.replace("\n", " ").replace("\r", " ").strip()
    return title or "Untitled Note"

def parse_yaml_frontmatter(content: str) -> dict:
    """Simple parser for YAML frontmatter in Markdown notes."""
    frontmatter = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            yaml_lines = parts[1].strip().split("\n")
            for line in yaml_lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    # Strip quotes or brackets if any
                    if val.startswith("[") and val.endswith("]"):
                        val = [item.strip().strip("'\"") for item in val[1:-1].split(",") if item.strip()]
                    elif val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    elif val.startswith("'") and val.endswith("'"):
                        val = val[1:-1]
                    frontmatter[key] = val
    return frontmatter

def scan_existing_wiki() -> dict:
    """Scans wiki/ recursively and maps capture IDs to their current file path."""
    id_map = {}
    if not os.path.exists(WIKI_DIR):
        return id_map
        
    for root, _, files in os.walk(WIKI_DIR):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    fm = parse_yaml_frontmatter(content)
                    if "id" in fm:
                        id_map[fm["id"]] = {
                            "path": filepath,
                            "category": fm.get("category", ""),
                            "title": fm.get("title", "")
                        }
                except Exception as e:
                    print(f"Warning: Failed to parse existing note {filepath}: {e}", file=sys.stderr)
    return id_map

def classify_content(note_type: str, content: str, metadata: dict) -> dict:
    """Queries Ollama to classify content and returns structured metadata."""
    # Truncate content if it's extremely long to fit prompt window
    content_snippet = content[:6000]
    
    prompt = f"Type: {note_type}\nMetadata: {json.dumps(metadata)}\n\nContent:\n{content_snippet}\n"
    
    max_retries = 3
    base_delay = 2
    raw_res = ""
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                OLLAMA_API_URL,
                json={
                    "model": MODEL_NAME,
                    "system": SYSTEM_PROMPT,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=30
            )
            response.raise_for_status()
            res_json = response.json()
            raw_res = res_json.get("response", "{}").strip()
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Warning: Ollama connection failed after {max_retries} attempts: {e}", file=sys.stderr)
            else:
                delay = base_delay ** (attempt + 1)
                print(f"Warning: Ollama query failed ({e}). Retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
                
    if raw_res:
        # Strip markdown block formatting if present
        if raw_res.startswith("```"):
            start = raw_res.find("{")
            end = raw_res.rfind("}")
            if start != -1 and end != -1:
                raw_res = raw_res[start:end+1]
        try:
            classification = json.loads(raw_res)
            if isinstance(classification, dict):
                return classification
        except Exception as e:
            print(f"Warning: Failed to parse LLM response JSON ({e}). Response was: {raw_res}", file=sys.stderr)

    # Fallback values
    fallback_title = metadata.get("title") or metadata.get("original_filename") or "Note"
    fallback_title = os.path.splitext(fallback_title)[0]
    return {
        "category": "Resources",
        "tags": [note_type],
        "summary": "Captured note without auto-summary.",
        "clean_title": sanitize_title(fallback_title)
    }

def organize_capture(capture_filepath: str, existing_notes: dict, force: bool = False):
    """Processes a single raw capture and saves it into wiki/."""
    try:
        with open(capture_filepath, "r", encoding="utf-8") as f:
            capture = json.load(f)
    except Exception as e:
        print(f"Error loading {capture_filepath}: {e}", file=sys.stderr)
        return
        
    capture_id = capture.get("id")
    if not capture_id:
        print(f"Error: Capture file {capture_filepath} is missing an 'id'.", file=sys.stderr)
        return

    # Check if already processed
    if capture_id in existing_notes and not force:
        # Note already exists and we are not forcing rebuild
        return

    print(f"Processing capture: {capture_id[:8]} ({capture.get('type')})")
    
    note_type = capture.get("type", "note")
    content = capture.get("content", "")
    metadata = capture.get("metadata", {})
    timestamp = capture.get("timestamp", datetime.now(timezone.utc).isoformat())
    
    # Classify
    meta = classify_content(note_type, content, metadata)
    
    # Extract & validate fields
    category = meta.get("category", "Resources").strip()
    # Normalize category capitalization
    matched_category = None
    for cat in CATEGORIES:
        if cat.lower() == category.lower():
            matched_category = cat
            break
    category = matched_category or "Resources"
    
    tags = meta.get("tags", [])
    if not isinstance(tags, list):
        tags = [tags]
    tags = [str(t).strip().lower() for t in tags if str(t).strip()]
    
    summary = meta.get("summary", "").strip()
    
    clean_title = sanitize_title(meta.get("clean_title", "Untitled"))
    
    # Determine original file path if applicable
    original_file = ""
    if note_type == "file":
        original_file = metadata.get("absolute_path") or metadata.get("original_filename") or ""

    # Check if this ID already had a note to handle category drift / renaming
    old_note_path = None
    if capture_id in existing_notes:
        old_note_path = existing_notes[capture_id]["path"]

    # Target path determination
    category_dir = os.path.join(WIKI_DIR, category)
    os.makedirs(category_dir, exist_ok=True)
    
    # Handle filename collision
    filename = f"{clean_title}.md"
    target_path = os.path.join(category_dir, filename)
    
    collision_counter = 1
    while os.path.exists(target_path):
        # If the existing file has the SAME capture ID, it's just an update, overwrite is fine
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                existing_fm = parse_yaml_frontmatter(f.read())
            if existing_fm.get("id") == capture_id:
                break
        except Exception:
            pass
            
        # Otherwise, append suffix
        filename = f"{clean_title}_{collision_counter}.md"
        target_path = os.path.join(category_dir, filename)
        collision_counter += 1

    # Format the markdown file
    yaml_tags_str = ", ".join(tags)
    markdown_content = f"""---
id: {capture_id}
title: "{clean_title}"
category: {category}
tags: [{yaml_tags_str}]
summary: "{summary}"
timestamp: {timestamp}
type: {note_type}
"""
    if original_file:
        # Escape backslashes for YAML frontmatter compatibility
        escaped_file = original_file.replace("\\", "\\\\")
        markdown_content += f"original_file: \"{escaped_file}\"\n"
        
    markdown_content += f"""---

{content}
"""

    # If the note moved categories/filenames, delete the old file
    if old_note_path and os.path.abspath(old_note_path) != os.path.abspath(target_path):
        try:
            os.remove(old_note_path)
            print(f"Moved note from {old_note_path} to {target_path}")
        except Exception as e:
            print(f"Warning: Failed to delete old note {old_note_path}: {e}", file=sys.stderr)
            
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
        
    print(f"Saved note: {target_path}")

def main():
    parser = argparse.ArgumentParser(description="SecondSelf Ingestion and LLM Classification")
    parser.add_argument("--force", action="store_true", help="Force re-classification and overwrite of existing notes")
    args = parser.parse_args()
    
    if not os.path.exists(RAW_DIR):
        print(f"Error: Raw directory '{RAW_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)
        
    existing_notes = scan_existing_wiki()
    
    # Process all files in raw/
    files_processed = 0
    for file in os.listdir(RAW_DIR):
        if file.endswith(".json") and file.startswith("capture_"):
            filepath = os.path.join(RAW_DIR, file)
            organize_capture(filepath, existing_notes, force=args.force)
            files_processed += 1
            
    print(f"\nProcessing complete. Scanned {files_processed} capture files.")

if __name__ == "__main__":
    main()
