import os
import sys
import json
import re
import pathlib
import urllib.parse
import pickle
from datetime import datetime
import numpy as np

# Try importing sentence_transformers
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Error: sentence-transformers is not installed. Please run pip install sentence-transformers", file=sys.stderr)
    sys.exit(1)

# Configurations
WIKI_DIR = "wiki"
CACHE_FILE = os.path.join(WIKI_DIR, ".embeddings_cache.json")
MODEL_NAME = "all-MiniLM-L6-v2"
SIM_THRESHOLD = 0.6
MAX_LINKS_PER_NOTE = 5
MIN_WORD_COUNT = 20

def parse_yaml_frontmatter(content: str) -> tuple[dict, str]:
    """Parses YAML frontmatter and returns (frontmatter_dict, remaining_body)."""
    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            yaml_block = parts[1].strip()
            body = parts[2]
            yaml_lines = yaml_block.split("\n")
            for line in yaml_lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    # Parse lists e.g., tags: [tag1, tag2] or links: []
                    if val.startswith("[") and val.endswith("]"):
                        val = [item.strip().strip("'\"") for item in val[1:-1].split(",") if item.strip()]
                    elif val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    elif val.startswith("'") and val.endswith("'"):
                        val = val[1:-1]
                    frontmatter[key] = val
    return frontmatter, body

def write_markdown_file(filepath: str, frontmatter: dict, body: str):
    """Writes the YAML frontmatter and body back to a Markdown file."""
    fm_lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            # Format list as YAML inline list
            items_str = ", ".join(f'"{item}"' for item in v)
            fm_lines.append(f"{k}: [{items_str}]")
        elif isinstance(v, (int, float)):
            fm_lines.append(f"{k}: {v}")
        else:
            # Escape strings if necessary
            val_str = str(v).replace('"', '\\"')
            fm_lines.append(f'{k}: "{val_str}"')
    fm_lines.append("---")
    
    full_content = "\n".join(fm_lines) + "\n\n" + body.strip() + "\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)

def clean_body_from_links(body: str) -> str:
    """Removes the Related Notes section from the body to avoid duplication."""
    parts = re.split(r'\n*### Related Notes\n', body, flags=re.IGNORECASE)
    return parts[0].strip()

def load_cache() -> dict:
    """Loads embedding cache from file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load embeddings cache ({e}). Initializing empty cache.", file=sys.stderr)
    return {}

def save_cache(cache: dict):
    """Saves embedding cache to file."""
    try:
        os.makedirs(WIKI_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save JSON embeddings cache ({e}).", file=sys.stderr)
        
    try:
        data_dir = "data"
        os.makedirs(data_dir, exist_ok=True)
        pkl_path = os.path.join(data_dir, "embeddings.pkl")
        with open(pkl_path, "wb") as f:
            pickle.dump(cache, f)
        print(f"Successfully saved pickle embeddings to {pkl_path}")
    except Exception as e:
        print(f"Warning: Failed to save pickle embeddings ({e}).", file=sys.stderr)

def main():
    if not os.path.exists(WIKI_DIR):
        print(f"Error: Wiki directory '{WIKI_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)
        
    print("Loading SentenceTransformer model...")
    model = SentenceTransformer(MODEL_NAME)
    
    # Load cache
    cache = load_cache()
    
    # Scan wiki for md files
    notes = []
    for root, _, files in os.walk(WIKI_DIR):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw_content = f.read()
                    
                    fm, body = parse_yaml_frontmatter(raw_content)
                    clean_body = clean_body_from_links(body)
                    
                    # Count words
                    word_count = len(clean_body.split())
                    
                    notes.append({
                        "path": filepath,
                        "id": fm.get("id", ""),
                        "title": fm.get("title", os.path.splitext(file)[0]),
                        "summary": fm.get("summary", ""),
                        "frontmatter": fm,
                        "body": clean_body,
                        "word_count": word_count,
                        "mtime": os.path.getmtime(filepath)
                    })
                except Exception as e:
                    print(f"Warning: Failed to parse {filepath}: {e}", file=sys.stderr)
                    
    # Filter notes that have enough content
    eligible_notes = [n for n in notes if n["word_count"] >= MIN_WORD_COUNT]
    print(f"Found {len(notes)} total notes, {len(eligible_notes)} are eligible for embedding (>= {MIN_WORD_COUNT} words).")
    
    # Compute embeddings
    updated_cache = {}
    embeddings = []
    
    for note in eligible_notes:
        filepath = note["path"]
        mtime = note["mtime"]
        cache_hit = False
        
        # Check cache
        if filepath in cache:
            cached_data = cache[filepath]
            if cached_data.get("mtime") == mtime:
                embedding = np.array(cached_data["embedding"], dtype=np.float32)
                cache_hit = True
                
        if not cache_hit:
            print(f"Computing embedding for: {note['title']}")
            # Embed title + summary + body for better semantic search
            text_to_embed = f"{note['title']} - {note['summary']}\n{note['body']}"
            embedding = model.encode(text_to_embed)
            # Normalize embedding
            embedding = embedding / np.linalg.norm(embedding)
            
        embeddings.append(embedding)
        updated_cache[filepath] = {
            "mtime": mtime,
            "embedding": embedding.tolist()
        }
        
    # Save the updated cache
    save_cache(updated_cache)
    
    if not eligible_notes:
        print("No notes to process for auto-linking.")
        return

    # Calculate similarity matrix
    emb_matrix = np.array(embeddings)
    # Since vectors are normalized, dot product is cosine similarity
    sim_matrix = np.dot(emb_matrix, emb_matrix.T)
    
    # Generate links
    links_map = {note["path"]: [] for note in notes}
    
    num_eligible = len(eligible_notes)
    for i in range(num_eligible):
        note_a = eligible_notes[i]
        path_a = note_a["path"]
        
        # Gather all similarities for note_a
        similarities = []
        for j in range(num_eligible):
            if i == j:
                continue
            sim = float(sim_matrix[i, j])
            if sim >= SIM_THRESHOLD:
                similarities.append((sim, eligible_notes[j]))
                
        # Sort by similarity descending
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        # Cap to MAX_LINKS_PER_NOTE
        top_similarities = similarities[:MAX_LINKS_PER_NOTE]
        
        for sim, note_b in top_similarities:
            links_map[path_a].append(note_b)
            
    # Update notes on disk
    for note in notes:
        filepath = note["path"]
        related = links_map.get(filepath, [])
        
        # Read the latest file contents to ensure we parse the exact latest body
        with open(filepath, "r", encoding="utf-8") as f:
            raw_content = f.read()
        fm, body = parse_yaml_frontmatter(raw_content)
        clean_body = clean_body_from_links(body)
        
        if related:
            # Format Related Notes section
            related_lines = ["### Related Notes"]
            yaml_links = []
            
            for note_b in related:
                note_b_abs_path = os.path.abspath(note_b["path"])
                note_b_uri = pathlib.Path(note_b_abs_path).as_uri()
                related_lines.append(f"- [[{note_b['title']}]](file:///{note_b_abs_path.replace(os.sep, '/')})")
                yaml_links.append(note_b["title"])
                
            new_body = clean_body + "\n\n" + "\n".join(related_lines)
            fm["links"] = yaml_links
            
            print(f"Linking: {note['title']} -> {yaml_links}")
        else:
            new_body = clean_body
            fm["links"] = []
            
        write_markdown_file(filepath, fm, new_body)
        
    print("\nAuto-linking completed successfully.")

if __name__ == "__main__":
    main()
