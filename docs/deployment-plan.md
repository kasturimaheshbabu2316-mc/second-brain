# SecondSelf — Streamlit Deployment Plan

Deploy the SecondSelf Streamlit app (`app.py`) to **Streamlit Community Cloud** so anyone can open a public URL, explore the knowledge graph, and ask questions against a bundled demo brain.

**Target URL pattern:** `https://secondself-<username>.streamlit.app`

**Related docs:** [architecture.md](./architecture.md) §8 · [Implementation-plan.md](./Implementation-plan.md) Phase 4.2 · [edge-case.md](./edge-case.md) §Deployment

---

## 1. Deployment Architecture

```
GitHub (public repo)
        │
        ▼
Streamlit Community Cloud
        │
        ├─▶ Main file: app.py
        ├─▶ Secrets: GROQ_API_KEY
        ├─▶ Bundled data: wiki/, data/graph.json, data/index.json
        │                 data/embeddings.pkl (recommended for demo)
        └─▶ Public URL
```

At runtime the app:

1. Loads pre-built `data/graph.json` and inlines it into the vis-network iframe (`lib/graph_view.py`) — no separate JSON fetch required.
2. Warms `all-MiniLM-L6-v2` via `@st.cache_resource` on first Ask or Process.
3. Calls Groq (`llama-3.1-8b-instant`) for classify + RAG when the user runs the pipeline or asks a question.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| **GitHub account** | Streamlit Cloud deploys from a connected repo |
| **Public repo** | Required for free Community Cloud tier (or use a private repo on paid plans) |
| **Groq API key** | [console.groq.com](https://console.groq.com/) — free tier is sufficient for demo traffic |
| **Local smoke test** | `streamlit run app.py` works with `.env` set |
| **Python 3.11+** | Recommended; matches project architecture docs |

---

## 3. Pre-Deployment Checklist

Complete these **before** pushing to GitHub and connecting Streamlit Cloud.

### 3.1 Privacy & demo data

- [ ] **Review `wiki/`** — only commit notes you are comfortable showing on a public URL (see SEC-05 in [edge-case.md](./edge-case.md)).
- [ ] **Do not commit `raw/`** — already in `.gitignore`; may contain originals (PDFs, personal captures).
- [ ] **Do not commit `.env`** — use Streamlit Secrets for `GROQ_API_KEY`.
- [ ] **Remove Obsidian metadata** — exclude `wiki/.obsidian/` from the repo (editor config, not needed for deploy).

### 3.2 Build demo artifacts locally

Run the full pipeline so committed data matches what the UI expects:

```bash
source .venv/bin/activate
python pipeline.py process    # classify → link → graph
python build_graph.py         # ensure data/graph.json is fresh
```

Verify locally:

```bash
streamlit run app.py
# Graph renders · Ask returns answers · Stats sidebar shows counts
```

### 3.3 Decide on embeddings strategy

| Option | Pros | Cons |
|--------|------|------|
| **A. Commit `data/embeddings.pkl`** (recommended for demo) | Fast first Ask; no re-embed on cold start | File grows with note count; currently ~40KB for 31 notes |
| **B. Omit embeddings (rebuild on first Process)** | Smaller repo; stays in sync with wiki edits | First pipeline run on Cloud is slow (~30–60s model download + embed) |

For the public demo, **Option A** is preferred. Temporarily allow the file in git:

```bash
# One-time: force-add despite .gitignore
git add -f data/embeddings.pkl
```

Longer term, consider a `data/demo/` subtree or a deploy script that copies prebuilt artifacts.

### 3.4 Files to commit for deploy

| Path | Commit? | Purpose |
|------|---------|---------|
| `app.py` | Yes | Streamlit entry point |
| `requirements.txt` | Yes | Python dependencies |
| `lib/`, `static/` | Yes | Shared code + graph template |
| `ask.py`, `capture.py`, `classify.py`, `link.py`, `build_graph.py`, `pipeline.py` | Yes | Backend imported by `app.py` |
| `wiki/**/*.md` | Yes | Demo knowledge base |
| `data/graph.json` | Yes | Pre-built graph for instant render |
| `data/index.json` | Yes | Pipeline state |
| `data/embeddings.pkl` | Yes (demo) | Pre-computed vectors |
| `.env`, `.env.example` | Example only | Never commit real secrets |
| `raw/` | **No** | Personal source captures |
| `wiki/.obsidian/` | **No** | Local editor config |
| `data/embeddings.pkl.bak` | **No** | Backup artifact |

---

## 4. Optional Repo Configuration

These files are not required today but improve reliability on Streamlit Cloud.

### 4.1 Python version — `.python-version` or `runtime.txt`

Streamlit Cloud reads `runtime.txt` if present:

```
python-3.11
```

Alternatively add `.python-version` with `3.11` for local parity.

### 4.2 Streamlit theme — `.streamlit/config.toml`

```toml
[server]
headless = true

[browser]
gatherUsageStats = false

[theme]
base = "light"
primaryColor = "#4F46E5"
```

### 4.3 Dependency pins

Current `requirements.txt` uses minimum versions. Before first production deploy, smoke-test with a fresh venv. If builds fail on Cloud, tighten pins (e.g. `streamlit==1.32.0`) after a successful local install.

`sentence-transformers` pulls PyTorch — expect a **2–5 minute** first Cloud build. No GPU is required (CPU inference is fine for demo scale).

---

## 5. Deploy to Streamlit Community Cloud

### Step 1 — Push to GitHub

```bash
git add app.py requirements.txt lib/ static/ wiki/ data/
git add -f data/embeddings.pkl   # if using Option A
git commit -m "Prepare SecondSelf for Streamlit Cloud deploy"
git push -u origin main
```

Ensure the repo is **public** (or that your Streamlit plan supports private repos).

### Step 2 — Create the app

1. Open [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **New app**.
3. Select the `second-self` repository, branch (`main`), and main file path: **`app.py`**.
4. Click **Advanced settings** if you need to set Python version (see §4.1).
5. Click **Deploy**.

Streamlit installs from `requirements.txt` and starts `streamlit run app.py`.

### Step 3 — Configure secrets

In the app dashboard → **Settings** → **Secrets**, add:

```toml
GROQ_API_KEY = "gsk_xxxxxxxxxxxxxxxx"
```

Streamlit injects these as environment variables. `lib/llm.py` reads them via `python-dotenv` and `os.environ` — no code changes needed.

**Never** paste the key into the repo, README, or commit messages. Rotate immediately if leaked (DEP-12).

### Step 4 — Wait for build

| Phase | Typical duration |
|-------|------------------|
| `pip install` (incl. torch + sentence-transformers) | 2–5 min |
| App boot | 10–30 s |
| First embedding model load (first Ask/Process) | 30–60 s |

The app may show **Running…** or spinners during cold start — expected (DEP-04, DEP-06).

---

## 6. Post-Deploy Verification

Run this checklist on the **live URL** (not just locally):

| # | Test | Expected result |
|---|------|-----------------|
| 1 | Open public URL | Page loads; title "SecondSelf"; no traceback |
| 2 | Knowledge graph | Nodes and edges visible; drag/zoom works |
| 3 | Sidebar stats | Wiki note / node / edge counts match committed data |
| 4 | Ask: *"What are my active projects?"* | Answer + source citations with relevance scores |
| 5 | Ask without API key (temporarily remove secret) | Clear error from `LLMError`; graph still loads (DEP-01) |
| 6 | Capture a note | Sidebar success message |
| 7 | Process new captures | Pipeline log; graph/stats update in-session |
| 8 | Refresh graph | Rebuild completes; graph re-renders |
| 9 | Re-open URL after idle | Cold start acceptable; graph still loads from committed JSON |

Record the live URL in `README.md` under **Live demo**.

---

## 7. Known Limitations (v1)

These are intentional tradeoffs for a free public demo — document them in the README if users will interact with Capture/Process.

| Limitation | Detail | Mitigation (future) |
|------------|--------|-------------------|
| **Ephemeral filesystem** | Captures and pipeline writes exist only until the container restarts or redeploys (DEP-10) | External storage (S3, Supabase, git-backed API) |
| **Public notes** | Anyone with the URL sees committed `wiki/` content (SEC-05) | Sanitized demo data; add auth (Streamlit-Authenticator) |
| **Single-user concurrency** | Simultaneous Process runs may race on `index.json` (XCP-14) | Document sequential use; add file locking |
| **Groq data processing** | Note text is sent to Groq for classify/ask (SEC-04) | Privacy note in README; self-hosted LLM later |
| **No persistent raw/** | Cloud container has no `raw/` from your machine | Demo is read-mostly; Capture is best-effort in-session |
| **Cold starts** | Free tier sleeps when idle (DEP-06) | Acceptable for portfolio demo |

**Demo narrative:** Lead with **Ask + Graph** (works from committed data). Treat **Capture → Process** as a live sandbox that resets on redeploy unless you add persistence.

---

## 8. Updating & Redeploying

Streamlit Cloud redeploys on push to the connected branch.

**Typical content update workflow:**

```bash
# Local: edit notes or run pipeline
python pipeline.py process
python build_graph.py

# Commit updated artifacts
git add wiki/ data/graph.json data/index.json
git add -f data/embeddings.pkl
git commit -m "Refresh demo knowledge base"
git push
```

If auto-deploy does not trigger (DEP-07), use **Manage app → Reboot app** or **Redeploy** in the dashboard.

**Secret rotation:** Update in Streamlit Secrets → Reboot app. Do not commit the new key.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Build fails on `sentence-transformers` / torch | Resource or version conflict | Pin versions; ensure Python 3.11; retry deploy |
| App loads but Ask errors immediately | Missing or invalid `GROQ_API_KEY` | Check Secrets spelling; reboot app |
| Graph empty | `data/graph.json` not committed or corrupt | Run `build_graph.py` locally; commit JSON |
| Ask very slow first time | Model download + embed cold start | Commit `embeddings.pkl`; use `@st.cache_resource` (already in `app.py`) |
| Process fails on Cloud | No `raw/` captures / API limits | Expected for empty demo; test with sidebar capture first |
| `ModuleNotFoundError` | Missing file in repo | Ensure all modules imported by `app.py` are pushed |
| vis-network blank | CDN blocked or bad JSON | Graph uses inline JSON (`lib/graph_view.py`); check browser console in iframe |
| Memory crash on Process | Embedding model + torch on small instance | Reduce wiki size; pre-commit embeddings; avoid force re-process on Cloud |

Check **Manage app → Logs** for stack traces. Reproduce locally with `streamlit run app.py` before debugging on Cloud.

---

## 10. Alternative: Hugging Face Spaces

Same app, different host — useful if Streamlit Cloud queues are long or you want HF integration.

1. Create a new **Space** → SDK: **Streamlit**.
2. Push the same repo (or a `deploy/` subtree).
3. Add `GROQ_API_KEY` under **Settings → Repository secrets**.
4. Entry point: `app.py`.

CPU Basic tier is sufficient (DEP-09). Architecture and secrets mapping are identical to §1.

---

## 11. Security Summary

- [ ] `.env` never committed; key only in Streamlit Secrets
- [ ] `raw/` stays gitignored
- [ ] Public `wiki/` reviewed for PII, credentials, private content
- [ ] Run `git log -p -- .env` before first public push — no historical leaks
- [ ] README states that Ask/Classify sends note excerpts to Groq

---

## 12. Success Criteria

Deployment is complete when:

- [ ] Public URL loads without errors
- [ ] Interactive graph renders from real committed notes
- [ ] Ask returns synthesized answers with source citations
- [ ] `GROQ_API_KEY` is configured via Secrets only
- [ ] README links to the live demo
- [ ] Pre-deploy checklist (§3) signed off

**Ship checkpoint:** Share the URL. Demo flow: ask a question → show answer with sources → explore the graph.

---

## 13. Future Enhancements (post-v1)

| Enhancement | Benefit |
|-------------|---------|
| Auth gate (Streamlit-Authenticator) | Private brain on public infra |
| Object storage for `raw/` + `wiki/` | Persistent Capture/Process on Cloud |
| CI job to rebuild `graph.json` + embeddings on merge | No manual `-f` git adds |
| `packages.txt` system deps | If PDF processing needs extra libs on Cloud |
| Health check / startup banner | Warn users during model download |
| Separate `demo/` branch | Keep personal `main` private; deploy branch is sanitized |

---

## Quick Reference

```bash
# Local preflight
streamlit run app.py

# Refresh deploy artifacts
python pipeline.py process && python build_graph.py

# Force-add embeddings for demo
git add -f data/embeddings.pkl

# Streamlit Cloud
# https://share.streamlit.io → New app → app.py → Secrets: GROQ_API_KEY
```
