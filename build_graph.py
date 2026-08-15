#!/usr/bin/env python3
"""Build data/graph.json from wiki notes (nodes + edges)."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import asdict

from lib.models import GraphEdge, GraphNode, WikiNote
from lib.storage import (
    load_index,
    read_wiki_notes,
    save_index,
    utc_now_iso,
    write_graph,
)

PREVIEW_CHARS = 200
_WIKILINK_RE = re.compile(r"\[\[([a-zA-Z0-9_-]+)\]\]")

NODE_REQUIRED = ("id", "label", "para", "tags", "summary", "content_preview", "group")
EDGE_REQUIRED = ("source", "target", "weight", "type")
META_REQUIRED = ("generated_at", "node_count", "edge_count")


def content_preview(body: str, limit: int = PREVIEW_CHARS) -> str:
    """Strip light markdown, collapse whitespace, cap length."""
    text = body or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = _WIKILINK_RE.sub(r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_>~|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def note_to_node(note: WikiNote) -> GraphNode:
    summary = (note.summary or "").strip()
    label = summary or note.id
    return GraphNode(
        id=note.id,
        label=label,
        para=note.para,
        tags=list(note.tags or []),
        summary=summary,
        content_preview=content_preview(note.body),
        group=note.para,
    )


def collect_link_ids(note: WikiNote) -> set[str]:
    """Union of frontmatter links[] and [[id]] wikilinks in body."""
    ids: set[str] = set()
    for link_id in note.links or []:
        lid = str(link_id).strip()
        if lid:
            ids.add(lid)
    ids.update(_WIKILINK_RE.findall(note.body or ""))
    return ids


def build_edges(
    notes: list[WikiNote],
    *,
    valid_ids: set[str],
) -> list[GraphEdge]:
    """
    Build undirected edges from frontmatter + body wikilinks.

    Deduplicates with key (min(source, target), max(source, target)).
    Skips self-links and targets that are not real notes.
    """
    edge_map: dict[tuple[str, str], GraphEdge] = {}
    skipped_missing: set[str] = set()

    for note in notes:
        for target in collect_link_ids(note):
            if target == note.id:
                continue
            if target not in valid_ids:
                skipped_missing.add(target)
                continue
            key = (min(note.id, target), max(note.id, target))
            if key not in edge_map:
                edge_map[key] = GraphEdge(
                    source=key[0],
                    target=key[1],
                    weight=1.0,
                    type="semantic",
                )

    for missing_id in sorted(skipped_missing):
        print(f"  Warning: skipping edge to unknown note id '{missing_id}'")

    return [edge_map[k] for k in sorted(edge_map)]


def validate_graph(graph: dict) -> list[str]:
    """Return a list of schema validation errors (empty if valid)."""
    errors: list[str] = []

    if not isinstance(graph, dict):
        return ["root must be an object"]

    for key in ("nodes", "edges", "metadata"):
        if key not in graph:
            errors.append(f"missing top-level key: {key}")

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    metadata = graph.get("metadata")

    if nodes is not None and not isinstance(nodes, list):
        errors.append("nodes must be a list")
    elif isinstance(nodes, list):
        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                errors.append(f"nodes[{i}] must be an object")
                continue
            for field in NODE_REQUIRED:
                if field not in node:
                    errors.append(f"nodes[{i}] missing field: {field}")

    if edges is not None and not isinstance(edges, list):
        errors.append("edges must be a list")
    elif isinstance(edges, list):
        for i, edge in enumerate(edges):
            if not isinstance(edge, dict):
                errors.append(f"edges[{i}] must be an object")
                continue
            for field in EDGE_REQUIRED:
                if field not in edge:
                    errors.append(f"edges[{i}] missing field: {field}")

    if metadata is not None and not isinstance(metadata, dict):
        errors.append("metadata must be an object")
    elif isinstance(metadata, dict):
        for field in META_REQUIRED:
            if field not in metadata:
                errors.append(f"metadata missing field: {field}")
        if (
            isinstance(nodes, list)
            and metadata.get("node_count") is not None
            and metadata["node_count"] != len(nodes)
        ):
            errors.append("metadata.node_count does not match len(nodes)")
        if (
            isinstance(edges, list)
            and metadata.get("edge_count") is not None
            and metadata["edge_count"] != len(edges)
        ):
            errors.append("metadata.edge_count does not match len(edges)")

    return errors


def build_graph() -> dict:
    """Parse wiki notes into a graph dict and write data/graph.json."""
    notes = read_wiki_notes()
    valid_ids = {n.id for n in notes}

    nodes = [note_to_node(n) for n in notes]
    edges = build_edges(notes, valid_ids=valid_ids)

    generated_at = utc_now_iso()
    graph = {
        "nodes": [asdict(n) for n in nodes],
        "edges": [asdict(e) for e in edges],
        "metadata": {
            "generated_at": generated_at,
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    }

    errors = validate_graph(graph)
    if errors:
        raise ValueError("Invalid graph schema:\n  - " + "\n  - ".join(errors))

    path = write_graph(graph)

    index = load_index()
    index.last_graph_build = generated_at
    save_index(index)

    print(
        f"Wrote {path} — "
        f"{graph['metadata']['node_count']} node(s), "
        f"{graph['metadata']['edge_count']} edge(s)."
    )
    return graph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build data/graph.json from wiki notes",
    )
    parser.parse_args(argv)

    try:
        build_graph()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
