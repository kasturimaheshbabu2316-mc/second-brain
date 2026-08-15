"""Build embeddable vis-network HTML for Streamlit (inline graph JSON)."""

from __future__ import annotations

import json

from lib.storage import PROJECT_ROOT

GRAPH_HTML_PATH = PROJECT_ROOT / "static" / "graph.html"


def build_graph_html(graph: dict | None, *, compact: bool = True) -> str:
    """
    Return self-contained graph HTML with INLINE_GRAPH injected.

    Streamlit iframes cannot fetch ../data/graph.json, so data is inlined.
    """
    template = GRAPH_HTML_PATH.read_text(encoding="utf-8")
    payload = graph if isinstance(graph, dict) else {
        "nodes": [],
        "edges": [],
        "metadata": {"generated_at": None, "node_count": 0, "edge_count": 0},
    }
    # Ensure JSON is safe inside a <script> tag
    inline = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    injection = f"<script>const INLINE_GRAPH = {inline};</script>\n"

    if "<script>" in template:
        # Inject immediately before the main script block
        html = template.replace("<script>", injection + "<script>", 1)
    else:
        html = injection + template

    if compact:
        # Fit better inside a Streamlit iframe
        html = html.replace(
            "height: calc(100% - 52px);",
            "height: calc(100% - 48px);",
            1,
        )
    return html
