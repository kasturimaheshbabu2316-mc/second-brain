---
id: "a8ab1fd7-3960-461e-96cf-6cf9f4afd23f"
title: "Edge Case Guide Analyzing the SecondSelf Architecture"
category: "Projects"
tags: ["edge-case", "edge-cases"]
summary: "A guide for categorizing critical edge cases, failure modes, and corner scenarios across the SecondSelf architecture."
timestamp: "2026-07-19T06:37:04.079410+00:00"
type: "file"
original_file: "C:\\Users\\kastu\\Desktop\\second brain\\doc\\edge-case.md"
links: ["SecondSelf Implementation Plan", "Architecture Design SecondSelf (AI Second Brain) Detailed Plan"]
---

# Edge Cases and Corner Scenarios: SecondSelf (AI Second Brain)

This document catalogs critical edge cases, failure modes, and corner scenarios across the four development phases of the **SecondSelf** architecture. Identifying and preparing for these scenarios ensures the system remains robust, predictable, and self-healing.

---

## Phase 1: The Archivist (Capture Pipeline)

### 1. File Capture

* **Zero-Byte or Empty Files:**
  * *Scenario:* The user runs the CLI capture on an empty file.
  * *Impact:* Embedding models and LLM classifiers fail on empty content.
  * *Mitigation:* Throw an error or warning on capture; require a minimum character count.
* **Large Files (e.g., 50MB PDFs or Codebases):**
  * *Scenario:* User tries to capture a very large file or directory.
  * *Impact:* Process runs out of memory, causes API timeouts, or exceeds LLM token limits in Phase 2.
  * *Mitigation:* Enforce a file size limit (e.g., 2MB) for direct text extraction. For larger files, log only the metadata and a truncated snippet.
* **Unsupported Binary File Types:**
  * *Scenario:* User captures a `.png`, `.zip`, or `.mp3` file.
  * *Impact:* UTF-8 text extraction crashes or reads garbage characters.
  * *Mitigation:* Implement a file type checker (whitelist extension/MIME types). Treat binaries as "metadata-only" capture.
* **Character Encoding Mismatch:**
  * *Scenario:* File is encoded in UTF-16, ISO-8859-1, or contains non-printable control characters.
  * *Impact:* Parser crashes with `UnicodeDecodeError`.
  * *Mitigation:* Read files with fallback encodings (`latin-1`, `cp1252`) or utilize `chardet` to detect encoding. Strip control characters.

### 2. Link Capture

* **Network & HTTP Failures:**
  * *Scenario:* URL returns `404 Not Found`, `403 Forbidden`, `500 Server Error`, or times out.
  * *Impact:* Capture script hangs or crashes.
  * *Mitigation:* Implement robust error handling with a short HTTP timeout (e.g., 5 seconds) and retry limit. Log a fallback note indicating connection failure.
* **JavaScript-Heavy SPAs / CAPTCHA Pages:**
  * *Scenario:* Capturing a link like a React App or a Cloudflare-protected page.
  * *Impact:* Fetching returns empty HTML or a "Please verify you are human" page.
  * *Mitigation:* Strip boilerplate script/styling tags. If extracted content is empty or contains CAPTCHA keywords, fall back to capturing only the URL and page title.
* **Malformed or Local URLs:**
  * *Scenario:* Capturing `ftp://...`, `file:///...`, or invalid strings like `http://localhost:8080`.
  * *Impact:* Library exceptions or security vulnerabilities (SSRF).
  * *Mitigation:* Validate URL schemes, whitelist `http` and `https`, and reject loopback/private IPs.

---

## Phase 2: The Librarian (Auto-Classify & Link)

### 1. LLM Classifier

* **API Downtime or Rate Limits (429):**
  * *Scenario:* Groq or Gemini API is offline, or rate limit is hit.
  * *Impact:* Auto-classification fails, blocking ingestion.
  * *Mitigation:* Implement an exponential backoff retry mechanism. Store the raw capture in a queue/retry folder if the API is offline.
* **Malformed LLM Output:**
  * *Scenario:* LLM outputs markdown formatting, extra text, or invalid JSON.
  * *Impact:* `json.loads()` crashes.
  * *Mitigation:* Use strict JSON mode or schema constraints. Parse using regex fallback, or request validation/repair from a parser block.
* **Illegal Title Characters (Windows/Linux Filenames):**
  * *Scenario:* LLM returns `clean_title: "What is AI? (Part 1)"`.
  * *Impact:* Creating `wiki/<Category>/What is AI? (Part 1).md` fails on Windows due to invalid characters (`?`).
  * *Mitigation:* Sanitize the title by stripping `\/:*?"<>|` characters before writing to disk.

### 2. File Organization

* **Filename Collisions:**
  * *Scenario:* Ingesting a new capture that results in the same `clean_title` as an existing note.
  * *Impact:* Overwrites existing files.
  * *Mitigation:* Check for existence. If title exists, append a unique suffix (e.g., `_1` or a timestamp hash).
* **Category Drift / Re-Classification:**
  * *Scenario:* An updated note changes category (e.g., `Projects` to `Archives`).
  * *Impact:* A duplicate file might be created in the new folder, leaving the old one behind (orphaned).
  * *Mitigation:* When updating/re-classifying, ensure the old file path is deleted or moved cleanly.

### 3. Embeddings & Auto-Linker

* **Zero Embeddings / Short Text:**
  * *Scenario:* Note has almost no text (e.g. just a URL or tag).
  * *Impact:* Embedding is all-zero or highly noisy, causing incorrect links.
  * *Mitigation:* Skip auto-linking if content size is below a specific threshold (e.g., 20 words).
* **Duplicate Mutual Links:**
  * *Scenario:* Re-running the auto-linker appends `[[Related Title]]` repeatedly to the bottom of the same file.
  * *Impact:* Messy files and duplicate links.
  * *Mitigation:* Deduplicate link parsing. Verify if link already exists in content or YAML frontmatter before appending.
* **Link Bloat (Dense Graph):**
  * *Scenario:* All notes are slightly related, creating a dense web where every note links to every other note.
  * *Impact:* Visually unreadable graph and slow rendering.
  * *Mitigation:* Cap the maximum number of auto-links per note (e.g., max 5 most similar links above threshold).

---

## Phase 3: The Cartographer (Visualizing the Brain)

### 1. Graph Data Model

* **Broken Markdown Links (Dangling Edges):**
  * *Scenario:* User deletes `wiki/Projects/OldProject.md`, but other files still contain `[[OldProject]]`.
  * *Impact:* The parser references a node that does not exist in `graph.json` or points to a dead link.
  * *Mitigation:* The graph exporter should filter out edges pointing to non-existent nodes, or render them as dotted "ghost" nodes.
* **Circular Link Dependencies:**
  * *Scenario:* Note A links to Note B, which links back to Note A.
  * *Impact:* Graph rendering engine loops infinitely or duplicates edges.
  * *Mitigation:* Treat links as bidirectional/undirected edges in the JSON exporter to prevent duplicate rendering of the same edge (`A -> B` and `B -> A`).

### 2. Interface Rendering

* **Scale / Performance Issues:**
  * *Scenario:* Knowledge base grows to 500+ notes.
  * *Impact:* Browser freezes trying to render the physics/forces of a large 3D/2D network graph.
  * *Mitigation:* Limit initial graph rendering to top/active categories, implement search filtering, or disable continuous physics simulation after initial layout stabilization.
* **Visual Overlap / Extreme Sizing:**
  * *Scenario:* A central hub note has 100 links, while others have 1.
  * *Impact:* The hub node dominates the entire screen, overlapping smaller nodes.
  * *Mitigation:* Use logarithmic scaling for node sizes based on connection degree rather than linear scaling.

---

## Phase 4: The Oracle (Ask Your Brain)

### 1. RAG Retrieval & Context

* **Empty Knowledge Base:**
  * *Scenario:* User asks a question before any captures are processed.
  * *Impact:* Retrieve step returns 0 notes; API query fails or LLM hallucinations occur.
  * *Mitigation:* Check for empty database and return a clean error page asking user to capture notes first.
* **Out-of-Domain Queries:**
  * *Scenario:* User asks "What is the capital of France?" when their second brain is about Machine Learning.
  * *Impact:* LLM hallucinates or crafts a generic response.
  * *Mitigation:* Instruct the LLM in the system prompt to explicitly state: *"I cannot find this information in your Second Brain"* if similarity scores of retrieved context are below a threshold (e.g., `0.3`).
* **Context Window Overflows:**
  * *Scenario:* The top 5 retrieved notes are extremely long, exceeding the LLM context limit.
  * *Impact:* API returns error (e.g., token limit exceeded) or truncates response.
  * *Mitigation:* Chunk markdown files during embedding/retrieval (e.g., chunk size 1000 characters) or retrieve only relevant paragraphs/summaries instead of full file content.

### Related Notes
- [[SecondSelf Implementation Plan]](file:///C:/Users/kastu/Desktop/second brain/wiki/Projects/SecondSelf Implementation Plan.md)
- [[Architecture Design SecondSelf (AI Second Brain) Detailed Plan]](file:///C:/Users/kastu/Desktop/second brain/wiki/Resources/Architecture Design SecondSelf (AI Second Brain) Detailed Plan.md)
