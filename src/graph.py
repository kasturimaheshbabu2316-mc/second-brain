import os
import sys
import json

WIKI_DIR = "wiki"
GRAPH_FILE = "graph.json"

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

def build_graph():
    if not os.path.exists(WIKI_DIR):
        print(f"Error: Wiki directory '{WIKI_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)
        
    notes = []
    title_to_id = {}
    id_to_note = {}
    
    # 1. First pass: Scan all files to extract titles and map to IDs
    for root, _, files in os.walk(WIKI_DIR):
        for file in files:
            if file.endswith(".md") and not file.startswith("."):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    fm = parse_yaml_frontmatter(content)
                    
                    note_id = fm.get("id")
                    title = fm.get("title", os.path.splitext(file)[0])
                    category = fm.get("category", "Resources")
                    summary = fm.get("summary", "")
                    links = fm.get("links", [])
                    
                    if not note_id:
                        continue
                        
                    note_data = {
                        "id": note_id,
                        "title": title,
                        "category": category,
                        "summary": summary,
                        "links": links,
                        "path": filepath
                    }
                    notes.append(note_data)
                    title_to_id[title.lower()] = note_id
                    id_to_note[note_id] = note_data
                except Exception as e:
                    print(f"Warning: Failed to parse existing note {filepath}: {e}", file=sys.stderr)
                    
    # 2. Second pass: Generate nodes and edges
    nodes = []
    edges = []
    seen_edges = set()
    
    for note in notes:
        # Node schema for vis.js
        nodes.append({
            "id": note["id"],
            "label": note["title"],
            "group": note["category"],
            "title": f"<b>{note['title']}</b><br><i>{note['category']}</i><br>{note['summary']}"
        })
        
        # Resolve links
        for target_title in note["links"]:
            target_id = title_to_id.get(target_title.lower())
            
            # Skip broken links / dangling edges
            if not target_id or target_id not in id_to_note:
                continue
                
            # Deduplicate bidirectional/undirected edges using sorted tuple
            edge_key = tuple(sorted([note["id"], target_id]))
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({
                    "from": note["id"],
                    "to": target_id
                })
                
    # 3. Export
    graph_data = {
        "nodes": nodes,
        "edges": edges
    }
    
    with open(GRAPH_FILE, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2, ensure_ascii=False)
        
    print(f"Graph exporter completed. Saved {len(nodes)} nodes and {len(edges)} edges to {GRAPH_FILE}")

if __name__ == "__main__":
    build_graph()
