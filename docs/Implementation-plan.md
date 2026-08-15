# SecondSelf — Phase-Wise Implementation Plan

A step-by-step build guide for SecondSelf, derived from `PROBLEM_STATEMENT.md` and `architecture.md`. Each phase is self-contained, testable on **real data**, and its output feeds the next phase.

---

## How to Use This Document

1. Complete phases **in order** — do not skip ahead.
2. Test every phase on **your own notes, links, and files** (not dummy data).
3. Check off acceptance criteria before moving to the next phase.
4. Each phase ends with a **ship checkpoint** — a working artifact you can demo.

**Total timeline:** 4 weeks (one phase per week).

---

## Phase Overview

| Phase | Name | Badge | Primary Output |
|-------|------|-------|----------------|
| 0 | Foundation | — | Repo scaffold, deps, shared libs |
| 1 | The Archivist | 🏅 The Archivist | `capture.py` + 10+ items in `raw/` |
| 2 | The Librarian | 🏅 The Librarian | Classified + linked `wiki/` (15+ items) |
| 3 | The Cartographer | 🏅 The Cartographer | `graph.json` + interactive graph |
| 4 | The Oracle | 🏅 The Oracle | `ask()` + Streamlit app on public URL |

```
Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4
 scaffold     capture     classify      graph        RAG +
              raw/        link wiki     visualize    deploy
```

---

## Phase 0 — Foundation (Day 0)

**Goal:** Scaffold the repo so every later phase has a consistent home for data and shared code.

### Tasks

- [ ] **0.1** Initialize git repo and create folder structure:

  ```
  secondself/
  ├── raw/
  ├── wiki/
  │   ├── Projects/
  │   ├── Areas/
  │   ├── Resources/
  │   └── Archives/
  ├── data/
  ├── lib/
  └── static/
  ```

- [ ] **0.2** Create `requirements.txt`:

  ```
  streamlit>=1.32
  groq>=0.4
  sentence-transformers>=2.3
  numpy>=1.24
  pyyaml>=6.0
  pypdf>=4.0
  requests>=2.31
  beautifulsoup4>=4.12
  python-dotenv>=1.0
  ```

- [ ] **0.3** Create virtual environment and install dependencies:

  ```bash
  python -m venv .venv
  source .venv/bin/activate   # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  ```

- [ ] **0.4** Create `.env.example` and `.gitignore`:

  ```
  # .env.example
  GROQ_API_KEY=your_key_here
  ```

  ```
  # .gitignore (minimum)
  .venv/
  .env
  data/embeddings.pkl
  __pycache__/
  *.pyc
  .DS_Store
  ```

- [ ] **0.5** Implement `lib/models.py` — shared dataclasses:

  | Model | Fields |
  |-------|--------|
  | `CaptureMeta` | `id`, `timestamp`, `type`, `source`, `original_filename`, `content_hash` |
  | `CaptureResult` | `id`, `path`, `type` |
  | `WikiNote` | `id`, `raw_id`, `para`, `tags`, `summary`, `created`, `links`, `body` |
  | `GraphNode` | `id`, `label`, `para`, `tags`, `summary`, `content_preview`, `group` |
  | `GraphEdge` | `source`, `target`, `weight`, `type` |
  | `AskResult` | `answer`, `sources` |

- [ ] **0.6** Implement `lib/storage.py` — filesystem helpers:

  | Function | Purpose |
  |----------|---------|
  | `generate_capture_id()` | `{YYYY-MM-DD}_{uuid8}` |
  | `write_raw_capture(meta, content)` | Create `raw/{id}/` folder |
  | `read_raw_captures()` | List all unprocessed raw items |
  | `write_wiki_note(note)` | Write `wiki/{para}/{id}.md` with YAML frontmatter |
  | `read_wiki_notes()` | Parse all wiki markdown files |
  | `load_index()` / `save_index()` | Read/write `data/index.json` |
  | `content_hash(data)` | SHA-256 for dedup / change detection |

- [ ] **0.7** Initialize `data/index.json`:

  ```json
  {
    "raw_processed": {},
    "embeddings_version": "all-MiniLM-L6-v2",
    "last_graph_build": null
  }
  ```

### Verification

- [ ] `python -c "from lib import models, storage"` runs without error
- [ ] All directories exist; `wiki/` has four PARA subfolders

### Deliverable

Repo scaffold with shared models and storage layer — no user-facing features yet.

---

## Phase 1 — The Archivist (Week 1)

**Goal:** One command captures any note, link, or file into `raw/` with timestamp + unique ID.

**Badge:** 🏅 The Archivist

### Tasks

- [ ] **1.1** Implement `capture.py` core functions:

  | Function | Input | Output |
  |----------|-------|--------|
  | `capture_note(text)` | Plain text / markdown string | `CaptureResult` |
  | `capture_link(url, notes="")` | URL + optional notes | `CaptureResult` |
  | `capture_file(path)` | Path to local file | `CaptureResult` |

  Each function must:
  1. Generate ID via `generate_capture_id()`
  2. Record ISO timestamp
  3. Write `raw/{id}/meta.json`
  4. Write content file (`content.md`, `content.txt`, or `content.{ext}`)
  5. Print confirmation: `Captured → raw/2026-07-06_a1b2c3d4`

- [ ] **1.2** Implement CLI with `argparse`:

  ```bash
  python capture.py note "Remember to review embeddings paper"
  python capture.py link "https://arxiv.org/abs/..."
  python capture.py file ./documents/resume.pdf
  python capture.py                          # interactive stdin mode
  ```

- [ ] **1.3** Handle edge cases:

  | Case | Behavior |
  |------|----------|
  | File does not exist | Print error, exit code 1 |
  | Empty note text | Reject with message |
  | Binary file | Copy as-is; record `original_filename` in meta |
  | Duplicate content | Warn (hash check); still allow capture |

- [ ] **1.4** Capture **10+ real items** from your own scattered information:

  Suggested mix:
  - 4–5 text notes (ideas, todos, journal snippets)
  - 3–4 bookmarks (articles, docs, repos)
  - 2–3 files (PDF, markdown doc, image with notes)

### File Deliverables

| File | Description |
|------|-------------|
| `capture.py` | CLI + capture functions |
| `raw/{id}/meta.json` | Metadata per capture |
| `raw/{id}/content.*` | Raw content per capture |

### Acceptance Criteria

- [ ] `raw/` and `wiki/` folder structure exists
- [ ] One command captures a note, a link, AND a file
- [ ] Every capture has a timestamp + unique ID
- [ ] 10+ real items captured (not test data)

### Ship Checkpoint

```bash
# Demo: capture three types in one session
python capture.py note "Career goal: transition to ML engineering by Q4"
python capture.py link "https://huggingface.co/sentence-transformers"
python capture.py file ~/Downloads/some-paper.pdf
ls raw/   # should show 10+ folders
```

---

## Phase 2 — The Librarian (Week 2)

**Goal:** Auto-classify raw captures with PARA + tags + summary, then auto-link related notes via embeddings.

**Badge:** 🏅 The Librarian

### Sub-Phase 2.1 — Auto-Classify (Days 1–3)

- [x] **2.1.1** Sign up for [Groq](https://console.groq.com/) and add `GROQ_API_KEY` to `.env`

- [x] **2.1.2** Implement `lib/llm.py`:

  | Function | Purpose |
  |----------|---------|
  | `call_llm(prompt, system="")` | Groq API wrapper with retry |
  | `classify_content(text)` | Returns `{para, tags, summary}` JSON |
  | `synthesize_answer(context, question)` | RAG answer (used in Phase 4) |

  Model: `llama-3.1-8b-instant`

- [x] **2.1.3** Implement text extraction helpers in `lib/storage.py` or `lib/extract.py`:

  | Source type | Extraction method |
  |-------------|-------------------|
  | `note` | Read `content.md` directly |
  | `link` | `requests` + `beautifulsoup4` strip HTML; fallback to URL string |
  | `file` (PDF) | `pypdf` text extraction; fallback to filename |

- [x] **2.1.4** Implement `classify.py`:

  ```
  For each raw/ item not in index.json["raw_processed"]:
      extract text → classify_content() → write wiki/{para}/{id}.md → update index.json
  ```

  Wiki note format:

  ```yaml
  ---
  id: a1b2c3d4
  raw_id: 2026-07-06_a1b2c3d4
  para: Projects
  tags: [ml, career]
  summary: "One-line summary"
  created: 2026-07-06T22:30:00Z
  links: []
  ---

  {cleaned body content}
  ```

- [x] **2.1.5** Run classifier on all Week 1 captures:

  ```bash
  python classify.py
  ```

- [x] **2.1.6** Manually spot-check 5 notes — verify PARA categories make sense

### File Deliverables

| File | Description |
|------|-------------|
| `capture.py` | CLI + capture functions |
| `raw/{id}/meta.json` | Metadata per capture |
| `raw/{id}/content.*` | Raw content per capture |

### Acceptance Criteria

- [ ] `raw/` and `wiki/` folder structure exists
- [ ] One command captures a note, a link, AND a file
- [ ] Every capture has a timestamp + unique ID
- [ ] 10+ real items captured (not test data)

### Ship Checkpoint

```bash
# Demo: capture three types in one session
python capture.py note "Career goal: transition to ML engineering by Q4"
python capture.py link "https://huggingface.co/sentence-transformers"
python capture.py file ~/Downloads/some-paper.pdf
ls raw/   # should show 10+ folders
```

---

## Phase 2 — The Librarian (Week 2)

**Goal:** Auto-classify raw captures with PARA + tags + summary, then auto-link related notes via embeddings.

**Badge:** 🏅 The Librarian

### Sub-Phase 2.1 — Auto-Classify (Days 1–3)

- [x] **2.1.1** Sign up for [Groq](https://console.groq.com/) and add `GROQ_API_KEY` to `.env`

- [x] **2.1.2** Implement `lib/llm.py`:

  | Function | Purpose |
  |----------|---------|
  | `call_llm(prompt, system="")` | Groq API wrapper with retry |
  | `classify_content(text)` | Returns `{para, tags, summary}` JSON |
  | `synthesize_answer(context, question)` | RAG answer (used in Phase 4) |

  Model: `llama-3.1-8b-instant`

- [x] **2.1.3** Implement text extraction helpers in `lib/storage.py` or `lib/extract.py`:

  | Source type | Extraction method |
  |-------------|-------------------|
  | `note` | Read `content.md` directly |
  | `link` | `requests` + `beautifulsoup4` strip HTML; fallback to URL string |
  | `file` (PDF) | `pypdf` text extraction; fallback to filename |

- [x] **2.1.4** Implement `classify.py`:

  ```
  For each raw/ item not in index.json["raw_processed"]:
      extract text → classify_content() → write wiki/{para}/{id}.md → update index.json
  ```

  Wiki note format:

  ```yaml
  ---
  id: a1b2c3d4
  raw_id: 2026-07-06_a1b2c3d4
  para: Projects
  tags: [ml, career]
  summary: "One-line summary"
  created: 2026-07-06T22:30:00Z
  links: []
  ---

  {cleaned body content}
  ```

- [x] **2.1.5** Run classifier on all Week 1 captures:

  ```bash
  python classify.py
  ```

- [x] **2.1.6** Manually spot-check 5 notes — verify PARA categories make sense

### Sub-Phase 2.2 — Auto-Link (Days 4–7)

- [x] **2.2.1** Implement `lib/embeddings.py`:

  | Function | Purpose |
  |----------|---------|
  | `load_model()` | Load `all-MiniLM-L6-v2` (cached) |
  | `embed_text(text)` | Return 384-dim vector |
  | `cosine_similarity(a, b)` | Similarity score |
  | `load_embeddings()` / `save_embeddings()` | `data/embeddings.pkl` |

- [x] **2.2.2** Implement `link.py`:

  ```
  For each wiki note (new or changed):
      embed(title + summary + body)
      compare vs all existing embeddings
      if similarity ≥ 0.75:
          add to frontmatter links[]
          append [[other-id]] in body (deduplicated)
      save embedding to embeddings.pkl
  ```

- [x] **2.2.3** Tune similarity threshold:

  | Threshold | Effect |
  |-----------|--------|
  | 0.65 | More links, some noise |
  | 0.75 | Start here — often too sparse on long notes |
  | **0.55** | **Tuned default** — after truncating embed text to summary+tags+800 body chars |
  | 0.80 | Fewer, higher-confidence links |

- [x] **2.2.4** Implement `pipeline.py` orchestrator:

  ```bash
  python pipeline.py classify   # classify only
  python pipeline.py link       # link only
  python pipeline.py process    # classify + link
  ```

- [x] **2.2.5** Capture 5+ additional real items, run full pipeline → 15+ total in `wiki/`

### File Deliverables

| File | Description |
|------|-------------|
| `lib/llm.py` | Groq client + classify/synthesize |
| `lib/embeddings.py` | sentence-transformers wrapper |
| `classify.py` | Raw → wiki classifier |
| `link.py` | Embedding similarity linker |
| `pipeline.py` | Orchestration script |
| `wiki/{para}/*.md` | 15+ classified notes |
| `data/embeddings.pkl` | Embedding index |
| `data/index.json` | Processing state |

### Acceptance Criteria

- [x] Any raw capture → category + tags + summary automatically
- [x] PARA categorization working (all four categories used appropriately)
- [x] Embeddings computed per note
- [x] Related notes auto-linked (no manual tagging)
- [x] Runs on 15+ real items → organized `wiki/`

### Ship Checkpoint

```bash
python pipeline.py process
find wiki/ -name "*.md" | wc -l    # ≥ 15
grep -r "\[\[" wiki/ | head        # wikilinks present
```

Open 2–3 linked notes side by side — confirm the connections are meaningful.

---

## Phase 3 — The Cartographer (Week 3)

**Goal:** Convert the linked wiki into a force-directed interactive graph you can explore.

**Badge:** 🏅 The Cartographer

### Sub-Phase 3.1 — Graph Data Model (Days 1–3)

- [x] **3.1.1** Implement `build_graph.py`:

  | Step | Logic |
  |------|-------|
  | Parse nodes | One node per `wiki/**/*.md` |
  | Parse edges | From `links[]` frontmatter + `[[id]]` in body |
  | Deduplicate | Edge key = `(min(source,target), max(source,target))` |
  | Enrich nodes | `label` = summary, `group` = para, `content_preview` = first 200 chars |
  | Export | Write `data/graph.json` |

- [x] **3.1.2** Validate `graph.json` schema:

  ```json
  {
    "nodes": [{ "id", "label", "para", "tags", "summary", "content_preview", "group" }],
    "edges": [{ "source", "target", "weight", "type" }],
    "metadata": { "generated_at", "node_count", "edge_count" }
  }
  ```

- [x] **3.1.3** Run builder and inspect output:

  ```bash
  python build_graph.py
  python -c "import json; g=json.load(open('data/graph.json')); print(g['metadata'])"
  ```

### Sub-Phase 3.2 — Interactive Graph (Days 4–7)

- [x] **3.2.1** Create `static/graph.html` with **vis-network**:

  - Load `graph.json` (inline or fetch)
  - Force-directed layout (Barnes-Hut physics)
  - Node colors by PARA `group`
  - Hover tooltip: `summary` + `content_preview`
  - Drag + zoom enabled
  - Optional pulse animation on nodes

- [x] **3.2.2** Physics config starting point:

  ```javascript
  physics: {
    barnesHut: { gravitationalConstant: -8000, springLength: 150 },
    stabilization: { iterations: 200 }
  }
  ```

- [x] **3.2.3** Test graph standalone in browser:

  ```bash
  python -m http.server 8000
  # Open http://localhost:8000/static/graph.html
  ```

- [x] **3.2.4** Verify interactions:

  | Interaction | Expected |
  |-------------|----------|
  | Hover node | Tooltip with note summary |
  | Drag node | Node moves, graph re-settles |
  | Scroll | Zoom in/out |
  | Click node | (Optional) highlight connected edges |

- [x] **3.2.5** Wire `build_graph.py` into `pipeline.py process` so graph rebuilds after linking

### File Deliverables

| File | Description |
|------|-------------|
| `build_graph.py` | Wiki → graph.json builder |
| `data/graph.json` | Exported graph data |
| `static/graph.html` | vis-network interactive viewer |

### Acceptance Criteria

- [x] Script builds nodes + edges from notes and exports clean JSON
- [x] Interactive force-directed graph renders from that JSON
- [x] Hover reveals note content
- [x] Drag + zoom work
- [x] Built from your real notes, not dummy data

### Ship Checkpoint

```bash
python build_graph.py
python -m http.server 8000
# Open graph in browser — explore your knowledge brain
```

---

## Phase 4 — The Oracle (Week 4)

**Goal:** Ask questions in plain English, get answers from your notes, and deploy everything as a public Streamlit app.

**Badge:** 🏅 The Oracle

### Sub-Phase 4.1 — Ask Your Brain (Days 1–3)

- [x] **4.1.1** Implement `ask.py`:

  ```python
  def ask(question: str, top_k: int = 5) -> AskResult:
  ```

  Pipeline:
  1. Embed question (`lib/embeddings.py`)
  2. Retrieve top-K notes by cosine similarity from `embeddings.pkl`
  3. Load full wiki bodies for retrieved IDs
  4. Build RAG prompt with note context
  5. Call `synthesize_answer()` via `lib/llm.py`
  6. Return `{ answer, sources: [{id, summary, relevance_score, para}] }`

- [x] **4.1.2** RAG prompt template:

  ```
  You are SecondSelf, answering from the user's personal knowledge base.
  Use ONLY the provided notes. If the answer isn't in the notes, say so.
  Cite sources as [note-id].

  Notes:
  {retrieved_notes}

  Question: {question}
  ```

- [x] **4.1.3** Guardrails:

  | Setting | Value |
  |---------|-------|
  | `top_k` | 5 (default) |
  | Temperature | 0.3 |
  | Max context | ~6000 tokens (truncate long notes) |
  | No relevant notes | Return "I don't have notes about that" |

- [x] **4.1.4** Test with 5+ real questions about your captured notes:

  ```bash
  python ask.py "What are my career goals?"
  python ask.py "What ML resources have I saved?"
  python ask.py "Summarize my active projects"
  ```

### Sub-Phase 4.2 — Streamlit App + Deployment (Days 4–7)

- [x] **4.2.1** Implement `app.py` layout:

  ```
  ┌────────────────────────────────────────────────────┐
  │  🧠 SecondSelf                    [Refresh Graph]  │
  ├────────────────────────────────────────────────────┤
  │  Ask your brain: [________________________] [Ask]  │
  │  Answer panel + source citations                 │
  ├────────────────────────────────────────────────────┤
  │  Interactive Knowledge Graph (vis-network)       │
  ├────────────────────────────────────────────────────┤
  │  Sidebar: Capture | Process | Stats              │
  └────────────────────────────────────────────────────┘
  ```

- [x] **4.2.2** Wire components:

  | UI Element | Backend |
  |------------|---------|
  | Ask bar | `ask.ask(question)` |
  | Graph | `st.components.v1.html()` embedding vis-network |
  | Capture form | `capture.capture_note(text)` |
  | Process button | `pipeline.process()` → rebuild graph |
  | Stats sidebar | Count nodes/edges from `graph.json` |
  | Refresh button | Re-run `build_graph.py`, reload component |

- [x] **4.2.3** Add caching:

  ```python
  @st.cache_resource
  def load_embeddings(): ...

  @st.cache_data
  def load_graph(): ...
  ```

- [x] **4.2.4** Test locally:

  ```bash
  streamlit run app.py
  ```

  Verify full flow: capture → process → graph updates → ask returns answer.

- [x] **4.2.5** Write `README.md`:

  - Project description + screenshot
  - Setup instructions (venv, deps, `.env`)
  - Usage (capture, process, ask)
  - Architecture overview (link to `architecture.md`)
  - Live demo URL

- [ ] **4.2.6** Push to GitHub (public repo) — deferred (next week)

- [ ] **4.2.7** Deploy to **Streamlit Community Cloud**: — deferred (next week)

  1. Connect GitHub repo at [share.streamlit.io](https://share.streamlit.io)
  2. Set main file: `app.py`
  3. Add secret: `GROQ_API_KEY`
  4. Pre-commit `wiki/`, `data/graph.json`, `data/embeddings.pkl` for demo
  5. Verify public URL loads

- [ ] **4.2.8** End-to-end test on deployed app: — deferred (next week)

  | Step | Action |
  |------|--------|
  | 1 | Open public URL |
  | 2 | Graph renders with real nodes |
  | 3 | Ask a question → get synthesized answer |
  | 4 | Capture a new note via sidebar |
  | 5 | Process → graph updates |

### File Deliverables

| File | Description |
|------|-------------|
| `ask.py` | RAG Q&A engine |
| `app.py` | Streamlit UI |
| `README.md` | Setup + usage docs |
| Live URL | `https://secondself-{user}.streamlit.app` (next week) |

### Acceptance Criteria

- [x] `ask()` returns answers synthesized from your own notes (retrieval + LLM)
- [x] One Streamlit app contains both the graph and the search bar
- [ ] Deployed live with a public URL — deferred (next week)
- [ ] Full pipeline works end to end in the deployed app — deferred (next week)

### Ship Checkpoint

Share your public URL. Demo: ask a question → see answer with sources → explore the graph.

---

## Final Integration Checklist

Before calling the project complete, verify the full pipeline:

```
Capture → Classify → Link → Graph → Ask → Deploy
```

- [ ] Public **GitHub repo** with clean README + setup instructions
- [ ] **Live deployed URL** — interactive graph + ask-your-brain search, both working
- [ ] End-to-end flow verified in production
- [ ] All 4 weekly milestones complete:

  | Milestone | Status |
  |-----------|--------|
  | Capture Pipeline (Phase 1) | ☐ |
  | Self-Organizing Wiki (Phase 2) | ☐ |
  | Living Brain (Phase 3) | ☐ |
  | SecondSelf Deployment (Phase 4) | ☐ |

---

## Dependency Map (Build Order)

```
Phase 0: lib/models.py, lib/storage.py, requirements.txt
    │
    ▼
Phase 1: capture.py
    │
    ▼
Phase 2: lib/llm.py → classify.py
         lib/embeddings.py → link.py → pipeline.py
    │
    ▼
Phase 3: build_graph.py → static/graph.html
    │
    ▼
Phase 4: ask.py → app.py → deploy
```

---

## Risk Register

| Risk | Phase | Mitigation |
|------|-------|------------|
| Groq API rate limits | 2, 4 | Batch classify; add retry with backoff |
| Embedding model slow on first load | 2, 4 | `@st.cache_resource` in Streamlit |
| Too many / too few auto-links | 2 | Tune threshold (0.65–0.80) |
| PDF text extraction fails | 2 | Fallback to filename; store raw file |
| Graph too cluttered | 3 | Filter by PARA category; limit edge weight display |
| Private notes on public URL | 4 | Use demo-safe data or document the tradeoff |
| Streamlit iframe sizing | 4 | Set explicit height on `st.components.v1.html()` |

---

## Quick Reference — Commands

```bash
# Phase 1
python capture.py note "..."
python capture.py link "https://..."
python capture.py file ./doc.pdf

# Phase 2
python classify.py
python link.py
python pipeline.py process

# Phase 3
python build_graph.py
python -m http.server 8000   # preview graph

# Phase 4
python ask.py "What are my career goals?"
streamlit run app.py
```

---

## References

- [PROBLEM_STATEMENT.md](./PROBLEM_STATEMENT.md) — weekly goals and acceptance criteria
- [architecture.md](./architecture.md) — data models, component design, deployment
