# SecondSelf

Your personal AI second brain: capture anything, auto-organize it with PARA, explore it as a living graph, and ask questions in plain English.

```
Capture → Classify → Link → Graph → Ask
```

## Features

- **Capture** notes, links, and files into `raw/`
- **Classify** into PARA wiki notes (`Projects` / `Areas` / `Resources` / `Archives`) via Groq
- **Link** related notes with local sentence-transformer embeddings
- **Explore** an interactive force-directed knowledge graph (vis-network)
- **Ask** questions answered only from your own notes (RAG)

## Setup (local)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set GROQ_API_KEY=...  (https://console.groq.com/)
```

## Usage

### Streamlit app (recommended)

```bash
python -m streamlit run app.py
# or: streamlit run app.py
```

In the UI:

1. **Sidebar → Capture** a quick note
2. **Process new captures** to classify, link, and rebuild the graph
3. **Ask your brain** a question and inspect cited sources
4. **Explore** the interactive graph (hover / drag / zoom)
5. **Refresh graph** after wiki changes

### CLI

```bash
# Capture
python capture.py note "Remember to review embeddings paper"
python capture.py link "https://arxiv.org/abs/1706.03762"
python capture.py file ./documents/resume.pdf

# Organize
python pipeline.py process          # classify → link → graph
python pipeline.py classify
python pipeline.py link
python pipeline.py graph

# Ask
python ask.py "What are my career goals?"
python ask.py "Summarize my active projects"

# Standalone graph (optional)
python -m http.server 8000
# open http://localhost:8000/static/graph.html
```

## Project layout

```
second-self/
├── app.py                 # Streamlit UI
├── ask.py                 # RAG Q&A
├── capture.py             # Ingest notes/links/files
├── classify.py            # PARA classification
├── link.py                # Embedding-based linking
├── build_graph.py         # wiki → data/graph.json
├── pipeline.py            # Orchestrator
├── lib/                   # Shared models, storage, LLM, embeddings
├── raw/                   # Captured source material
├── wiki/                  # Organized markdown notes (Obsidian-friendly)
├── data/                  # graph.json, index.json, embeddings.pkl
├── static/graph.html      # Standalone graph viewer
└── docs/                  # Architecture + implementation plan
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for data models, component design, and end-to-end flow.  
Step-by-step build guide: [docs/Implementation-plan.md](docs/Implementation-plan.md).

## Live demo

Public Streamlit Cloud deployment is planned for next week. For now, run locally with `streamlit run app.py`.

## Notes

- `GROQ_API_KEY` is required for classify + ask (never commit `.env`)
- First embedding run downloads `all-MiniLM-L6-v2` (~80MB)
- `wiki/` can be opened directly as an Obsidian vault; body `[[wikilinks]]` power Obsidian’s graph
