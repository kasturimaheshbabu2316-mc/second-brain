#!/usr/bin/env python3
"""SecondSelf Streamlit app — ask your brain + explore the knowledge graph."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import streamlit as st
import streamlit.components.v1 as components

from ask import ask
from build_graph import build_graph
from capture import CaptureError, capture_note
from lib.deploy import inject_streamlit_secrets, is_streamlit_cloud
from lib.embeddings import EmbeddingError, load_embeddings, load_model
from lib.graph_view import build_graph_html
from lib.llm import LLMError, is_groq_configured
from lib.storage import ensure_dirs, load_graph, load_index, read_wiki_notes
from pipeline import process

GRAPH_HEIGHT = 620


st.set_page_config(
    page_title="SecondSelf",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_streamlit_secrets()
ensure_dirs()


@st.cache_resource
def cached_embedding_model():
    """Warm the sentence-transformers model once per process."""
    return load_model()


@st.cache_data
def cached_graph(version: int):
    """Load graph.json; version bumps invalidate after rebuild."""
    _ = version
    return load_graph()


@st.cache_data
def cached_embeddings_count(version: int) -> int:
    _ = version
    return len(load_embeddings())


def _cache_version() -> int:
    return int(st.session_state.get("cache_version", 0))


def _bump_cache() -> None:
    st.session_state["cache_version"] = _cache_version() + 1
    cached_graph.clear()
    cached_embeddings_count.clear()


def _run_captured(fn, *args, **kwargs):
    """Run fn while capturing stdout/stderr for the UI."""
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        result = fn(*args, **kwargs)
    return result, buf.getvalue()


def render_deploy_notices() -> None:
    """Surface Cloud-specific limits and missing API key without blocking the graph."""
    if not is_groq_configured():
        st.warning(
            "**Ask** and **Process** need a Groq API key. "
            "Local: set `GROQ_API_KEY` in `.env`. "
            "Streamlit Cloud: add it under **Settings → Secrets**."
        )

    if is_streamlit_cloud():
        st.info(
            "Hosted demo: the graph and bundled notes load from the repo. "
            "Captures and pipeline changes are **session-only** and reset on redeploy."
        )


def render_sidebar() -> None:
    st.sidebar.header("Capture")
    # Clear must happen before the widget with key="capture_text" is created
    if st.session_state.pop("_clear_capture_text", False):
        st.session_state["capture_text"] = ""

    note_text = st.sidebar.text_area(
        "Quick note",
        key="capture_text",
        height=120,
        placeholder="Capture a thought, task, or insight…",
    )
    if st.sidebar.button("Capture note", use_container_width=True):
        try:
            result = capture_note(note_text, source="cli")
            st.session_state["_clear_capture_text"] = True
            st.session_state["_capture_flash"] = f"Captured → raw/{result.id}"
            st.rerun()
        except CaptureError as exc:
            st.sidebar.error(str(exc))

    flash = st.session_state.pop("_capture_flash", None)
    if flash:
        st.sidebar.success(flash)

    st.sidebar.divider()
    st.sidebar.header("Pipeline")
    force = st.sidebar.checkbox("Force re-process", value=False)
    if st.sidebar.button("Process new captures", type="primary", use_container_width=True):
        if not is_groq_configured():
            st.sidebar.error(
                "Set GROQ_API_KEY first (.env locally, or Streamlit Secrets on Cloud)."
            )
        else:
            with st.sidebar.status("Running classify → link → graph…", expanded=True) as status:
                try:
                    cached_embedding_model()
                    rc, log = _run_captured(process, force=force)
                    if log.strip():
                        st.code(log[-4000:], language="text")
                    if rc == 0:
                        _bump_cache()
                        status.update(label="Pipeline complete", state="complete")
                        st.sidebar.success("Wiki, links, and graph updated.")
                    else:
                        status.update(label="Pipeline failed", state="error")
                        st.sidebar.error("Pipeline exited with an error — see log above.")
                except (LLMError, EmbeddingError, ValueError) as exc:
                    status.update(label="Pipeline failed", state="error")
                    st.sidebar.error(str(exc))

    st.sidebar.divider()
    st.sidebar.header("Stats")
    graph = cached_graph(_cache_version()) or {}
    meta = graph.get("metadata") or {}
    wiki_count = len(read_wiki_notes())
    emb_count = cached_embeddings_count(_cache_version())
    index = load_index()

    st.sidebar.metric("Wiki notes", wiki_count)
    st.sidebar.metric("Graph nodes", meta.get("node_count", len(graph.get("nodes") or [])))
    st.sidebar.metric("Graph edges", meta.get("edge_count", len(graph.get("edges") or [])))
    st.sidebar.metric("Embeddings", emb_count)
    if index.last_graph_build:
        st.sidebar.caption(f"Last graph build: {index.last_graph_build}")
    st.sidebar.caption(f"Raw processed: {len(index.raw_processed)}")


def render_ask() -> None:
    st.subheader("Ask your brain")
    col_q, col_btn = st.columns([5, 1])
    with col_q:
        question = st.text_input(
            "Question",
            key="ask_question",
            label_visibility="collapsed",
            placeholder="What are my career goals?",
        )
    with col_btn:
        ask_clicked = st.button("Ask", type="primary", use_container_width=True)

    if ask_clicked:
        if not (question or "").strip():
            st.warning("Enter a question first.")
        else:
            if not is_groq_configured():
                st.error(
                    "Set GROQ_API_KEY first (.env locally, or Streamlit Secrets on Cloud)."
                )
                st.session_state.pop("ask_result", None)
            else:
                with st.spinner("Searching your notes… (first run may load the embedding model)"):
                    try:
                        cached_embedding_model()
                        result = ask(question.strip())
                        st.session_state["ask_result"] = result
                    except (LLMError, EmbeddingError) as exc:
                        st.error(str(exc))
                        st.session_state.pop("ask_result", None)

    result = st.session_state.get("ask_result")
    if result is None:
        return

    st.markdown(result.answer)
    if result.sources:
        st.markdown("**Sources**")
        for src in result.sources:
            st.markdown(
                f"- `{src.id}` · {src.para} · score **{src.relevance_score:.3f}** — "
                f"{src.summary}"
            )


def render_graph_section() -> None:
    st.subheader("Knowledge graph")
    graph = cached_graph(_cache_version())
    html = build_graph_html(graph)
    components.html(html, height=GRAPH_HEIGHT, scrolling=False)


def main() -> None:
    if "cache_version" not in st.session_state:
        st.session_state["cache_version"] = 0

    title_l, title_r = st.columns([5, 1])
    with title_l:
        st.title("🧠 SecondSelf")
        st.caption("Your personal AI second brain — capture, organize, explore, ask.")
    with title_r:
        st.write("")
        if st.button("Refresh graph", use_container_width=True):
            try:
                with st.spinner("Rebuilding graph…"):
                    _run_captured(build_graph)
                _bump_cache()
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    render_deploy_notices()
    render_sidebar()
    render_ask()
    st.divider()
    render_graph_section()


if __name__ == "__main__":
    main()
