# SecondSelf — Edge Cases & Corner Scenarios

A reference catalog of edge cases, failure modes, and corner scenarios for SecondSelf. Use this during implementation and testing to ensure each pipeline stage degrades gracefully.

**Sources:** [architecture.md](./architecture.md), [Implementation-plan.md](./Implementation-plan.md)

---

## How to Read This Document

Each entry follows this format:

| Column | Meaning |
|--------|---------|
| **ID** | Stable reference (e.g. `CAP-01`) |
| **Scenario** | What can go wrong or behave unexpectedly |
| **Impact** | Severity: `Low` / `Medium` / `High` / `Critical` |
| **Expected Behavior** | What the system should do |
| **Component** | Affected module or file |
| **Phase** | Build phase where this matters most |

**Severity guide:**

- **Critical** — Data loss, security breach, or full pipeline failure
- **High** — Incorrect output or broken user-facing feature
- **Medium** — Degraded experience; workaround exists
- **Low** — Cosmetic or rare; safe to defer post-v1

---

## Summary by Phase

| Phase | Component | Edge Case Count |
|-------|-----------|-----------------|
| 0 | Foundation & Storage | 12 |
| 1 | Capture | 18 |
| 2 | Classify | 22 |
| 2 | Link & Embeddings | 20 |
| 3 | Graph Builder | 14 |
| 3 | Interactive Graph | 12 |
| 4 | Ask (RAG) | 18 |
| 4 | Streamlit App | 14 |
| 4 | Deployment | 12 |
| — | Cross-Cutting / Pipeline | 15 |

---

## Phase 0 — Foundation & Storage

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| FND-01 | `raw/` or `wiki/` directory missing | High | Auto-create on first write; log info message | `lib/storage.py` |
| FND-02 | `data/index.json` missing or corrupt | High | Initialize fresh index with defaults; warn user that processing history is lost | `lib/storage.py` |
| FND-03 | `data/index.json` is valid JSON but wrong schema | Medium | Migrate or reset with warning; do not crash silently | `lib/storage.py` |
| FND-04 | `data/embeddings.pkl` missing on first run | Low | Treat as empty dict `{}`; create on first embed | `lib/embeddings.py` |
| FND-05 | `data/embeddings.pkl` corrupt or wrong format | High | Backup corrupt file as `.bak`; rebuild from wiki notes | `lib/embeddings.py` |
| FND-06 | Two processes write `index.json` simultaneously | Medium | Use atomic write (write temp → rename); last write wins with merge if possible | `lib/storage.py` |
| FND-07 | Disk full during capture or write | Critical | Catch `OSError`; print clear error; do not leave half-written folder | `lib/storage.py` |
| FND-08 | Filename with special characters (`/`, `\0`, emoji) | Medium | Sanitize `original_filename` in meta; preserve content | `lib/storage.py` |
| FND-09 | Wiki note moved between PARA folders manually | Medium | `read_wiki_notes()` scans all subfolders; graph rebuild picks up new location | `lib/storage.py` |
| FND-10 | YAML frontmatter contains unescaped `:` or `"` | Medium | Use safe YAML dumper; quote strings; validate on read | `lib/storage.py` |
| FND-11 | Note body contains `---` that breaks frontmatter parsing | Medium | Use `---` delimiter only at file start; body after closing `---` | `lib/storage.py` |
| FND-12 | `GROQ_API_KEY` env var missing | High | Fail fast with actionable message: "Set GROQ_API_KEY in .env" | `lib/llm.py` |

---

## Phase 1 — Capture (`capture.py`)

### Input Validation

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| CAP-01 | Empty note text (`""` or whitespace only) | Low | Reject with message; exit code 1; no folder created | `capture.py` |
| CAP-02 | Note text exceeds reasonable size (e.g. 1 MB) | Medium | Accept and store; warn that classify may truncate | `capture.py` |
| CAP-03 | File path does not exist | Medium | Print error with path; exit code 1 | `capture.py` |
| CAP-04 | File path is a directory, not a file | Medium | Print error; exit code 1 | `capture.py` |
| CAP-05 | Invalid URL format (no scheme, malformed) | Medium | Reject or store as note text with warning | `capture.py` |
| CAP-06 | URL with only whitespace | Low | Reject with message | `capture.py` |

### Content Types

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| CAP-07 | Binary file (image, zip, exe) | Medium | Copy as-is; set `type: file`; classify later may use filename only | `capture.py` |
| CAP-08 | Zero-byte file | Low | Capture with empty content; meta records `content_hash` of empty | `capture.py` |
| CAP-09 | Very large file (>100 MB) | Medium | Copy with warning; may slow pipeline; consider size limit config | `capture.py` |
| CAP-10 | File with no extension | Low | Store as `content.bin`; record `original_filename` | `capture.py` |
| CAP-11 | Symlink to file | Low | Copy target content (or dereference); record resolved path in meta | `capture.py` |
| CAP-12 | Unicode / emoji / RTL text in note | Low | Store as UTF-8; preserve exactly | `capture.py` |
| CAP-13 | Note with only markdown formatting, no prose | Low | Accept; LLM classifies from structure/headers | `capture.py` |

### Duplication & Identity

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| CAP-14 | Duplicate content (same hash as existing capture) | Low | Warn user; still create new capture with new ID (captures are append-only) | `capture.py` |
| CAP-15 | Same URL captured twice | Low | Warn on hash/URL match; allow duplicate (user may re-capture intentionally) | `capture.py` |
| CAP-16 | ID collision (same date + uuid8 clash) | Low | Regenerate uuid until unique; astronomically rare | `lib/storage.py` |
| CAP-17 | Capture at UTC midnight (date boundary) | Low | Use UTC consistently; ID date matches capture timestamp date | `lib/storage.py` |

### CLI & Interactive Mode

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| CAP-18 | Interactive stdin mode; user sends EOF (Ctrl+D) immediately | Low | Exit gracefully with message | `capture.py` |
| CAP-19 | Unknown CLI subcommand | Low | Print usage help; exit code 2 | `capture.py` |
| CAP-20 | `capture.py file` with relative path from different cwd | Medium | Resolve to absolute path before copy; store absolute path in meta | `capture.py` |

---

## Phase 2 — Classify (`classify.py`, `lib/llm.py`)

### Text Extraction

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| CLS-01 | PDF is scanned image (no text layer) | High | `pypdf` returns empty; fallback summary = filename; tag `needs-ocr` | `classify.py` |
| CLS-02 | PDF is password-protected | High | Skip text extraction; classify from filename + meta; log warning | `classify.py` |
| CLS-03 | PDF corrupted or truncated | Medium | Catch parse error; fallback to filename | `classify.py` |
| CLS-04 | PDF with mixed languages | Low | Extract all text; LLM handles multilingual content | `classify.py` |
| CLS-05 | URL returns 404 / 403 / 500 | Medium | Store URL in wiki body; classify from URL string + any user notes | `classify.py` |
| CLS-06 | URL fetch timeout (>30s) | Medium | Abort fetch; classify from URL string only | `classify.py` |
| CLS-07 | URL points to PDF or binary (not HTML) | Medium | Do not parse as HTML; store URL; summary from filename/URL path | `classify.py` |
| CLS-08 | URL requires authentication (paywall, login) | Medium | Fetch fails; classify from URL + user notes in `content.txt` | `classify.py` |
| CLS-09 | JavaScript-rendered SPA (empty HTML body) | Medium | Extract `<title>` and meta description; fallback to URL | `classify.py` |
| CLS-10 | Link `content.txt` has URL + user notes below | Low | Fetch URL text; append user notes to extracted content | `classify.py` |
| CLS-11 | Note/file with no extractable text | Medium | Classify from metadata only (filename, type, timestamp) | `classify.py` |
| CLS-12 | Extracted text is extremely long (>50k tokens) | Medium | Truncate to first ~4000 tokens before LLM call; full text stays in wiki body | `lib/llm.py` |

### LLM Classification

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| CLS-13 | LLM returns invalid JSON | High | Retry once; on second failure fallback: `para: Resources`, `tags: []`, `summary: first 100 chars` | `lib/llm.py` |
| CLS-14 | LLM returns JSON with wrong `para` value (e.g. "Project" not "Projects") | Medium | Normalize to valid PARA enum; default `Resources` if unmappable | `lib/llm.py` |
| CLS-15 | LLM returns empty tags or summary | Medium | Accept; use content preview as summary fallback | `lib/llm.py` |
| CLS-16 | LLM hallucinates tags unrelated to content | Low | Accept (v1); user can manually edit wiki later | `lib/llm.py` |
| CLS-17 | Groq API rate limit (429) | High | Exponential backoff retry (3 attempts); pause between batch items | `lib/llm.py` |
| CLS-18 | Groq API down / network error | High | Retry with backoff; skip item and log; continue batch | `lib/llm.py` |
| CLS-19 | Invalid or expired API key (401) | Critical | Fail with clear message; do not partially corrupt wiki | `lib/llm.py` |
| CLS-20 | Content in non-English language | Low | LLM still classifies; tags may be English or source language | `lib/llm.py` |
| CLS-21 | Ambiguous content (fits multiple PARA categories) | Low | LLM picks best fit; acceptable inconsistency across similar notes | `lib/llm.py` |
| CLS-22 | Raw capture already in `index.json` but content hash changed | Medium | Re-classify; overwrite wiki note; update index hash | `classify.py` |

### Wiki Write

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| CLS-23 | Wiki file already exists for same ID | Medium | Overwrite on re-classify; preserve `links[]` if re-linking separately | `classify.py` |
| CLS-24 | PARA folder does not exist (e.g. typo in LLM output) | Medium | Create folder or remap to `Resources/` | `lib/storage.py` |
| CLS-25 | Classify run with zero unprocessed raw items | Low | Print "Nothing to classify"; exit 0 | `classify.py` |

---

## Phase 2 — Link & Embeddings (`link.py`, `lib/embeddings.py`)

### Embedding Computation

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| LNK-01 | Note text empty after strip (title + summary + body all empty) | Medium | Skip embedding; note appears in graph with no semantic links | `link.py` |
| LNK-02 | Note text very short (1–2 words) | Low | Embed anyway; similarity may be noisy | `link.py` |
| LNK-03 | First note in wiki (no existing embeddings) | Low | Embed and store; no links created; normal path | `link.py` |
| LNK-04 | `sentence-transformers` model download fails (offline) | High | Clear error with install/download instructions; halt link step | `lib/embeddings.py` |
| LNK-05 | Embedding model version changed (`embeddings_version` mismatch) | High | Re-embed all notes; update `embeddings_version` in index | `lib/embeddings.py` |
| LNK-06 | Note content changed but embedding not updated | High | Compare content hash in index; re-embed on mismatch | `link.py` |
| LNK-07 | Embedding vector is all zeros (model error) | Medium | Log warning; skip similarity for that note | `lib/embeddings.py` |

### Similarity & Linking

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| LNK-08 | No notes above similarity threshold | Low | Note stands alone; `links: []`; valid outcome | `link.py` |
| LNK-09 | Note similar to itself (always highest) | Low | Exclude self from comparison; never self-link | `link.py` |
| LNK-10 | Threshold too low → spurious links | Medium | Tune threshold (0.65–0.80); document in README | `link.py` |
| LNK-11 | Threshold too high → no links in sparse wiki | Medium | Lower threshold or capture more related content | `link.py` |
| LNK-12 | Symmetric links (A→B and B→A) | Low | Write bidirectional links in both notes' frontmatter and body | `link.py` |
| LNK-13 | Duplicate `[[id]]` already in body | Low | Deduplicate before append | `link.py` |
| LNK-14 | Linked note ID does not exist in wiki | Medium | Skip invalid link; log warning; do not write broken wikilink | `link.py` |
| LNK-15 | Many notes (>500) — O(n²) comparison slow | Medium | Accept for v1; batch or ANN index in future | `link.py` |
| LNK-16 | Notes in different languages linked incorrectly | Low | Embeddings are multilingual; some false positives acceptable | `link.py` |
| LNK-17 | Re-run link on all notes | Medium | Idempotent: merge links, deduplicate; do not duplicate `[[id]]` | `link.py` |
| LNK-18 | Manual edit removes a wikilink from body but not frontmatter | Low | `build_graph` reads both sources; dedupe edges; frontmatter is source of truth on next link run | `link.py` |

### Embeddings Index

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| LNK-19 | Wiki note deleted but embedding remains in `.pkl` | Low | Orphan embedding ignored at retrieval; optional cleanup pass | `lib/embeddings.py` |
| LNK-20 | `embeddings.pkl` out of sync with wiki (manual file delete) | Medium | Rebuild embeddings from all wiki notes on `link.py` full run | `lib/embeddings.py` |

---

## Phase 3 — Graph Builder (`build_graph.py`)

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| GRB-01 | Wiki folder empty (no notes yet) | Medium | Export `graph.json` with empty nodes/edges; metadata `node_count: 0` | `build_graph.py` |
| GRB-02 | Single note, no links | Low | One node, zero edges; valid graph | `build_graph.py` |
| GRB-03 | `[[wikilink]]` points to non-existent note ID | Medium | Skip edge; log warning; do not crash | `build_graph.py` |
| GRB-04 | Duplicate edges (same source/target from body + frontmatter) | Low | Deduplicate by `(min, max)` key | `build_graph.py` |
| GRB-05 | Edge in frontmatter `links[]` but not in body (or vice versa) | Low | Union both sources; one edge in graph | `build_graph.py` |
| GRB-06 | Note missing required frontmatter fields | Medium | Use defaults: `para: Resources`, `summary: id`, `tags: []` | `build_graph.py` |
| GRB-07 | `content_preview` from body with newlines/markdown | Low | Strip markdown; collapse whitespace; cap at 200 chars | `build_graph.py` |
| GRB-08 | Node `label` empty | Low | Fallback to `summary` or `id` | `build_graph.py` |
| GRB-09 | Very large wiki (1000+ notes) | Medium | Build may be slow; graph UI may lag; acceptable for v1 | `build_graph.py` |
| GRB-10 | Malformed markdown file (no frontmatter) | Medium | Skip file or parse body-only with generated defaults; log warning | `build_graph.py` |
| GRB-11 | Circular link chains (A→B→C→A) | Low | Valid graph; no special handling needed | `build_graph.py` |
| GRB-12 | `graph.json` write fails mid-serialization | Medium | Write to temp file; atomic rename; never leave partial JSON | `build_graph.py` |
| GRB-13 | Stale `graph.json` (wiki updated, graph not rebuilt) | Medium | UI shows old graph until `build_graph.py` or Process button runs | `build_graph.py` |
| GRB-14 | Node ID contains characters invalid in JSON/JS | Low | IDs are alphanumeric; sanitize if ever extended | `build_graph.py` |

---

## Phase 3 — Interactive Graph (`static/graph.html`, vis-network)

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| GRV-01 | `graph.json` empty or missing | Medium | Show empty canvas with message: "No notes yet" | `static/graph.html` |
| GRV-02 | `graph.json` malformed JSON | High | Catch parse error; show error message in UI | `static/graph.html` |
| GRV-03 | Node with very long label/summary | Low | Truncate in tooltip; full text on click if implemented | `static/graph.html` |
| GRV-04 | Graph with 100+ nodes — cluttered layout | Medium | Physics stabilization; user can zoom/drag; filter by PARA in future | `static/graph.html` |
| GRV-05 | Graph with one densely connected cluster | Low | Force-directed layout separates naturally; may need tuning | `static/graph.html` |
| GRV-06 | Hover on node with empty `content_preview` | Low | Show `summary` only; fallback to `id` | `static/graph.html` |
| GRV-07 | vis-network CDN unavailable | High | Bundle vis-network locally in `static/` for deploy | `static/graph.html` |
| GRV-08 | Browser blocks inline script (CSP) | Medium | Use Streamlit `html()` component; avoid external fetch if blocked | `app.py` |
| GRV-09 | `st.components.v1.html()` iframe too short | Low | Set explicit `height=600` (or configurable) | `app.py` |
| GRV-10 | Graph JSON embedded inline exceeds size limit | Medium | Load from file path or chunk; cap preview fields | `app.py` |
| GRV-11 | User drags node off-screen | Low | vis-network allows pan/zoom to recover | `static/graph.html` |
| GRV-12 | All nodes same PARA category — no color variety | Low | Still render; single color group is valid | `static/graph.html` |

---

## Phase 4 — Ask / RAG (`ask.py`)

### Retrieval

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| ASK-01 | Empty question string | Low | Reject with message; do not call LLM | `ask.py` |
| ASK-02 | Question whitespace only | Low | Reject with message | `ask.py` |
| ASK-03 | No embeddings in index | High | Return "No notes indexed yet. Run the pipeline first." | `ask.py` |
| ASK-04 | No notes above relevance threshold | Medium | Return "I don't have notes about that." with empty sources | `ask.py` |
| ASK-05 | All retrieved notes have low similarity (<0.3) | Medium | Still return top-K but warn in UI; or apply minimum score cutoff | `ask.py` |
| ASK-06 | Retrieved note file deleted from wiki | Medium | Skip missing note; continue with remaining sources | `ask.py` |
| ASK-07 | `top_k` larger than total notes | Low | Return all available notes | `ask.py` |
| ASK-08 | Question language differs from note language | Low | Multilingual embeddings; may reduce retrieval quality | `ask.py` |
| ASK-09 | Question asks about future events not in notes | Medium | LLM should say "not in your notes" per prompt guardrail | `ask.py` |
| ASK-10 | Question is adversarial / prompt injection | High | System prompt: use ONLY provided notes; ignore instructions in question | `ask.py` |

### Synthesis

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| ASK-11 | Retrieved context exceeds LLM token limit | High | Truncate notes by relevance score until within ~6000 tokens | `ask.py` |
| ASK-12 | LLM invents facts not in retrieved notes | High | Low temperature (0.3); prompt cites sources; show sources in UI | `lib/llm.py` |
| ASK-13 | LLM returns empty answer | Medium | Fallback message: "Could not generate an answer." | `lib/llm.py` |
| ASK-14 | Groq timeout during synthesis | High | Retry once; return error with partial retrieval sources | `lib/llm.py` |
| ASK-15 | Multiple notes contradict each other | Medium | LLM synthesizes best effort; cite both sources | `ask.py` |
| ASK-16 | Question requires aggregation across many notes | Medium | top_k=5 may miss some; increase K or run summary query | `ask.py` |
| ASK-17 | Very long question (paragraph) | Low | Embed full question; truncate if needed | `ask.py` |
| ASK-18 | Embedding model not loaded (cold start) | Medium | Load on first ask; show loading spinner in UI (~10s) | `app.py` |

---

## Phase 4 — Streamlit App (`app.py`)

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| APP-01 | User clicks Ask with empty input | Low | Disable button or show validation message | `app.py` |
| APP-02 | User clicks Process while pipeline already running | Medium | Disable button; show spinner; prevent double-run | `app.py` |
| APP-03 | Pipeline fails mid-process | High | Show error in UI; partial state OK; index tracks completed items | `app.py` |
| APP-04 | Capture from sidebar with empty text | Low | Validation message; no write | `app.py` |
| APP-05 | Streamlit session rerun clears unsent question | Low | Use `st.session_state` to persist input | `app.py` |
| APP-06 | `@st.cache_resource` stale after wiki update | Medium | Clear cache on Process complete; or `cache_data` with file mtime key | `app.py` |
| APP-07 | Graph does not refresh after Process | Medium | Call `st.cache_data.clear()` or bump cache key on rebuild | `app.py` |
| APP-08 | Long-running classify blocks UI | Medium | Show progress bar or spinner; consider background thread post-v1 | `app.py` |
| APP-09 | Multiple browser tabs open same app | Low | Each session independent; filesystem writes may race — document single-user | `app.py` |
| APP-10 | User uploads file via Streamlit (if added) | Medium | Route through `capture_file()`; same edge cases as CLI | `app.py` |
| APP-11 | Markdown answer contains raw HTML/script | Medium | Streamlit sanitizes by default; do not use `unsafe_allow_html` for answers | `app.py` |
| APP-12 | Source citation links to missing note | Low | Show ID as text only; no crash | `app.py` |
| APP-13 | App started without `.env` in dev | High | Clear error on first LLM call | `app.py` |
| APP-14 | `streamlit run` from wrong working directory | Medium | Resolve paths relative to project root (`Path(__file__).parent`) | `app.py` |

---

## Phase 4 — Deployment

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| DEP-01 | `GROQ_API_KEY` not set in Streamlit Secrets | Critical | App loads graph; Ask fails with clear error | Streamlit Cloud |
| DEP-02 | Private/sensitive notes in public repo | Critical | Document risk; use demo-safe wiki data; never commit `.env` | Ops |
| DEP-03 | `embeddings.pkl` not committed (in `.gitignore`) | High | First ask on deploy re-embeds all notes (slow); or commit for demo | Ops |
| DEP-04 | Embedding model download on Streamlit cold start | High | First load ~30–60s; show spinner; `@st.cache_resource` | `app.py` |
| DEP-05 | Repo exceeds Streamlit/resource limits | Medium | Trim `raw/` binaries; commit slim `wiki/` + prebuilt `graph.json` | Ops |
| DEP-06 | Streamlit Cloud sleep / spin-down | Low | Cold start on first visit; acceptable for demo | Ops |
| DEP-07 | Git push does not trigger redeploy | Low | Manual redeploy from Streamlit dashboard | Ops |
| DEP-08 | `requirements.txt` pin mismatch breaks build | High | Pin major versions; test deploy in CI or manually | Ops |
| DEP-09 | HF Spaces alternative — GPU not needed | Low | CPU sufficient for sentence-transformers inference | Ops |
| DEP-10 | User captures new note on deployed app | Medium | Writes to ephemeral filesystem; lost on redeploy unless external storage | Ops |
| DEP-11 | CORS / fetch `graph.json` from static path fails | Medium | Inline JSON in HTML component for deploy | `app.py` |
| DEP-12 | API key leaked in commit history | Critical | Rotate key immediately; use Secrets; scan with `git log -p` | Ops |

---

## Cross-Cutting — Pipeline & State

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| XCP-01 | Run `classify` before any captures exist | Low | No-op with message | `classify.py` |
| XCP-02 | Run `link` before `classify` | Medium | No wiki notes; no-op with message | `link.py` |
| XCP-03 | Run `build_graph` before `link` | Low | Graph with nodes, possibly no edges | `build_graph.py` |
| XCP-04 | Run `ask` before pipeline complete | High | Graceful message if no embeddings/wiki | `ask.py` |
| XCP-05 | `pipeline.py process` interrupted (Ctrl+C) | Medium | Index reflects completed items; re-run resumes unprocessed | `pipeline.py` |
| XCP-06 | Manual deletion of `raw/` folder item | Low | Orphan wiki note remains; index still references raw_id | Ops |
| XCP-07 | Manual deletion of wiki note | Low | Orphan embedding; broken links in other notes; rebuild cleans edges | Ops |
| XCP-08 | Manual edit of wiki frontmatter | Low | Next link run may overwrite links; graph rebuild picks up edits | Ops |
| XCP-09 | Clock skew / timezone in timestamps | Low | Store all timestamps as UTC ISO 8601 | `lib/storage.py` |
| XCP-10 | Git merge conflict in `data/index.json` | Medium | Resolve manually; prefer union of `raw_processed` | Ops |
| XCP-11 | Run pipeline on machine A, open app on machine B | Low | Local-first; sync via git; document workflow | Ops |
| XCP-12 | Python version < 3.11 | Medium | Document 3.11+ in README; type hints may fail on older | Ops |
| XCP-13 | Windows vs macOS path separators | Medium | Use `pathlib.Path` everywhere | `lib/storage.py` |
| XCP-14 | Concurrent CLI capture + Streamlit Process | Medium | Filesystem race possible; document single-user / sequential use | Ops |
| XCP-15 | Full pipeline re-run from scratch | Medium | Delete `data/index.json` + `wiki/` + `embeddings.pkl`; re-process all `raw/` | Ops |

---

## Security & Privacy Edge Cases

| ID | Scenario | Impact | Expected Behavior | Component |
|----|----------|--------|-------------------|-----------|
| SEC-01 | Captured note contains API keys / passwords | Critical | User responsibility; warn in README; never auto-commit `raw/` | Ops |
| SEC-02 | URL fetch follows redirect to malicious site | Medium | Set request timeout; optional domain allowlist post-v1 | `classify.py` |
| SEC-03 | PDF contains embedded JavaScript | Low | `pypdf` extracts text only; do not execute | `classify.py` |
| SEC-04 | LLM prompt includes user PII from notes | Medium | Data sent to Groq; document in privacy section of README | `lib/llm.py` |
| SEC-05 | Public deploy exposes personal notes | Critical | Use sanitized demo data; add auth in future | Ops |
| SEC-06 | XSS via note content in graph tooltip | Medium | Escape HTML in vis-network tooltip rendering | `static/graph.html` |
| SEC-07 | Path traversal in `capture.py file ../../../etc/passwd` | High | Resolve and validate path stays within allowed directories | `capture.py` |

---

## Testing Checklist

Use this checklist to verify edge-case handling before each phase ship checkpoint.

### Phase 1
- [ ] CAP-01, CAP-03, CAP-07, CAP-14, CAP-18

### Phase 2
- [ ] CLS-01, CLS-05, CLS-13, CLS-17, LNK-03, LNK-08, LNK-14

### Phase 3
- [ ] GRB-01, GRB-02, GRB-03, GRB-04, GRV-01, GRV-09

### Phase 4
- [ ] ASK-01, ASK-04, ASK-10, ASK-11, APP-02, APP-07, DEP-01, DEP-04

### Pre-Deploy
- [ ] DEP-02, DEP-03, DEP-10, DEP-12, SEC-01, SEC-05

---

## Quick Reference — Fallback Defaults

| Situation | Fallback |
|-----------|----------|
| LLM JSON parse fails | `para: Resources`, `tags: []`, `summary: <first 100 chars>` |
| PDF unreadable | Summary = `original_filename` |
| URL fetch fails | Classify from URL string + user notes |
| No similar notes | `links: []`, standalone graph node |
| No relevant notes for question | "I don't have notes about that." |
| Missing frontmatter field | `para: Resources`, `tags: []`, `summary: <id>` |
| Missing `GROQ_API_KEY` | Fail fast with setup instructions |
| Empty wiki / graph | Valid empty state with user message |

---

## References

- [architecture.md](./architecture.md) — Section 11 (Error Handling) and component design
- [Implementation-plan.md](./Implementation-plan.md) — Risk Register and per-phase task notes
- [PROBLEM_STATEMENT.md](./PROBLEM_STATEMENT.md) — Acceptance criteria per week
