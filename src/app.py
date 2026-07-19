import os
import sys
import json
import pathlib
import urllib.parse
import subprocess
import requests
import re
import numpy as np
import streamlit as st
from datetime import datetime, timezone

# Load local SentenceTransformer for Q&A embeddings
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    st.error("Error: sentence-transformers is not installed. Run pip install sentence-transformers.")
    sys.exit(1)

# App Configuration
st.set_page_config(page_title="SecondSelf — Your AI Second Brain", layout="wide", initial_sidebar_state="expanded")

# Custom HSL Dark Aesthetic CSS
st.markdown("""
<style>
    /* Dark Theme Styling */
    .stApp {
        background-color: #0B0F19;
        color: #F8FAFC;
        font-family: 'Inter', sans-serif;
    }
    
    /* Header styling */
    .brain-header {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #6366F1, #3B82F6, #10B981);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    
    .brain-subheader {
        font-size: 1.1rem;
        color: #94A3B8;
        margin-bottom: 2rem;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid #1E293B;
    }
    
    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        background-color: #0F172A;
        padding: 10px 20px;
        border-radius: 12px;
        border: 1px solid #1E293B;
    }
    
    .stTabs [data-baseweb="tab"] {
        color: #94A3B8 !important;
        font-weight: 600;
    }
    
    .stTabs [aria-selected="true"] {
        color: #6366F1 !important;
        border-bottom-color: #6366F1 !important;
    }
    
    /* Cards and Containers */
    .card {
        background-color: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    
    .card-title {
        font-weight: 700;
        font-size: 1.2rem;
        color: #F8FAFC;
        margin-bottom: 0.5rem;
    }
    
    /* Badges */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.6rem;
        font-size: 0.75rem;
        font-weight: 600;
        border-radius: 9999px;
        margin-right: 0.5rem;
    }
    
    .badge-projects { background-color: #FF6B6B33; color: #FF6B6B; border: 1px solid #FF6B6B; }
    .badge-areas { background-color: #4DABF733; color: #4DABF7; border: 1px solid #4DABF7; }
    .badge-resources { background-color: #51CF6633; color: #51CF66; border: 1px solid #51CF66; }
    .badge-archives { background-color: #ADB5BD33; color: #ADB5BD; border: 1px solid #ADB5BD; }
</style>
""", unsafe_allow_html=True)

# Helper function to load env
def load_env() -> dict:
    env = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("'\"")
    return env

ENV_VARS = load_env()
GEMINI_API_KEY = ENV_VARS.get("GEMINI_API_KEY")

# Initalize local Embeddings Model
@st.cache_resource
def load_embedding_model():
    return SentenceTransformer("all-MiniLM-L6-v2")

model = load_embedding_model()

# Helper to execute capture backend pipeline
def run_ingestion_pipeline():
    try:
        # Run classification
        subprocess.run([sys.executable, "src/organize.py"], check=True)
        # Run auto-linker
        subprocess.run([sys.executable, "src/embeddings.py"], check=True)
        # Run graph exporter
        subprocess.run([sys.executable, "src/graph.py"], check=True)
        return True
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        return False

# Parse markdown frontmatter helper
def parse_yaml_frontmatter(content: str) -> tuple[dict, str]:
    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            yaml_block = parts[1].strip()
            body = parts[2]
            for line in yaml_block.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if v.startswith("[") and v.endswith("]"):
                        v = [item.strip().strip("'\"") for item in v[1:-1].split(",") if item.strip()]
                    elif v.startswith('"') and v.endswith('"'):
                        v = v[1:-1]
                    elif v.startswith("'") and v.endswith("'"):
                        v = v[1:-1]
                    frontmatter[k] = v
    return frontmatter, body

# Load notes helper
def load_all_notes() -> list[dict]:
    notes = []
    wiki_path = pathlib.Path("wiki")
    if not wiki_path.exists():
        return notes
    for path in wiki_path.rglob("*.md"):
        if path.name.startswith("."):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            fm, body = parse_yaml_frontmatter(content)
            # Remove related notes section from the parsed body
            body_clean = re.split(r'\n*### Related Notes\n', body, flags=re.IGNORECASE)[0].strip()
            notes.append({
                "path": str(path),
                "title": fm.get("title", path.stem),
                "category": fm.get("category", "Resources"),
                "summary": fm.get("summary", ""),
                "tags": fm.get("tags", []),
                "timestamp": fm.get("timestamp", ""),
                "body": body_clean,
                "id": fm.get("id", "")
            })
        except Exception:
            pass
    return notes

# RAG Search Function
def rag_query(query: str, notes: list[dict], k: int = 3) -> tuple[str, list[dict]]:
    if not notes:
        return "Your knowledge base is empty. Please capture some notes first.", []
        
    # Get query embedding
    query_emb = model.encode(query)
    query_emb = query_emb / np.linalg.norm(query_emb)
    
    # Load embedding cache
    cache = {}
    cache_path = "wiki/.embeddings_cache.json"
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cache = json.load(f)
        except Exception:
            pass
            
    # Calculate similarities
    scored_notes = []
    for note in notes:
        note_path = note["path"]
        if note_path in cache:
            note_emb = np.array(cache[note_path]["embedding"])
            # dot product (since vectors are normalized)
            sim = float(np.dot(query_emb, note_emb))
            scored_notes.append((sim, note))
        else:
            # Fallback compute
            text = f"{note['title']} - {note['summary']}\n{note['body']}"
            note_emb = model.encode(text)
            note_emb = note_emb / np.linalg.norm(note_emb)
            sim = float(np.dot(query_emb, note_emb))
            scored_notes.append((sim, note))
            
    # Sort and take top K
    scored_notes.sort(key=lambda x: x[0], reverse=True)
    top_matches = [note for sim, note in scored_notes[:k] if sim >= 0.25]
    
    if not top_matches:
        return "I cannot find any relevant information in your Second Brain to answer this question.", []
        
    # Construct context
    context_parts = []
    for idx, note in enumerate(top_matches):
        context_parts.append(f"Source [{idx+1}] Title: {note['title']}\nContent:\n{note['body']}")
    context_str = "\n\n---\n\n".join(context_parts)
    
    system_instruction = (
        "You are 'The Oracle', the RAG search and Q&A engine for SecondSelf.\n"
        "Synthesize a clear, detailed, and comprehensive answer to the user's question using ONLY the provided note contexts.\n"
        "For facts you present, cite the source number (e.g. [1], [2]) inline based on the sources given.\n"
        "If the context notes do not contain the information needed to answer the question, state: "
        "'I cannot find this information in your Second Brain.'\n"
        "Do not make up facts or use external knowledge."
    )
    
    prompt = f"Context Notes:\n{context_str}\n\nQuestion: {query}\n\nAnswer:"
    
    # Query LLM
    response_text = ""
    if GEMINI_API_KEY:
        try:
            # REST API call to Google Gemini 1.5 Flash
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": f"{system_instruction}\n\n{prompt}"}]}
                ]
            }
            res = requests.post(url, json=payload, timeout=20)
            res.raise_for_status()
            res_json = res.json()
            response_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            st.warning(f"Failed to query Gemini API ({e}). Falling back to local Ollama...")
            
    if not response_text:
        # Fallback to local Ollama qwen2.5:0.5b
        try:
            res = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5:0.5b",
                    "system": system_instruction,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            res.raise_for_status()
            response_text = res.json().get("response", "No response received.")
        except Exception as e:
            response_text = f"Error: Could not query LLM backend (Ollama or Gemini). {e}"
            
    return response_text, top_matches

import re

# App Header
st.markdown("<div class='brain-header'>SecondSelf</div>", unsafe_allow_html=True)
st.markdown("<div class='brain-subheader'>Your Interactive, Self-Organizing AI Second Brain</div>", unsafe_allow_html=True)

# Main UI Tabs
tab_explore, tab_ask, tab_capture, tab_directory = st.tabs([
    "🌐 Knowledge Graph", 
    "🔮 Ask Your Brain", 
    "📥 Capture Intake", 
    "📂 Notes Directory"
])

notes = load_all_notes()

# Sidebar Statistics
with st.sidebar:
    st.markdown("### 📊 Brain Stats")
    total_notes = len(notes)
    proj_count = sum(1 for n in notes if n["category"] == "Projects")
    area_count = sum(1 for n in notes if n["category"] == "Areas")
    res_count = sum(1 for n in notes if n["category"] == "Resources")
    arch_count = sum(1 for n in notes if n["category"] == "Archives")
    
    st.markdown(f"**Total Notes**: `{total_notes}`")
    st.markdown(f"- 🔴 **Projects**: `{proj_count}`")
    st.markdown(f"- 🔵 **Areas**: `{area_count}`")
    st.markdown(f"- 🟢 **Resources**: `{res_count}`")
    st.markdown(f"- ⚪ **Archives**: `{arch_count}`")
    
    st.markdown("---")
    st.markdown("### ⚙️ Environment")
    if GEMINI_API_KEY:
        st.success("Cloud Gemini API: **Active**")
    else:
        st.info("Local Ollama Model: **Active**")

# ==================== TAB 1: EXPLORE (GRAPH VISUALIZATION) ====================
with tab_explore:
    st.markdown("### Interactive Knowledge Network")
    st.markdown("Click nodes to inspect their summary, or drag them around to interact with the physics engine.")
    
    graph_file = "graph.json"
    if not os.path.exists(graph_file):
        # Generate initial graph file if missing
        subprocess.run([sys.executable, "src/graph.py"])
        
    if os.path.exists(graph_file):
        with open(graph_file, "r", encoding="utf-8") as f:
            graph_data = json.load(f)
            
        nodes_js = json.dumps(graph_data.get("nodes", []))
        edges_js = json.dumps(graph_data.get("edges", []))
        
        # Vis.js Dark Theme Template with detail slide-out side panel inside iframe
        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
            <style type="text/css">
                body {{
                    background-color: #0B0F19;
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    color: #F8FAFC;
                }}
                #mynetwork {{
                    width: 70%;
                    height: 580px;
                    float: left;
                    background-color: #0B0F19;
                }}
                #detail-panel {{
                    width: 28%;
                    height: 580px;
                    float: right;
                    background-color: #0F172A;
                    border-left: 1px solid #1E293B;
                    padding: 20px;
                    box-sizing: border-box;
                    overflow-y: auto;
                }}
                h3 {{
                    color: #6366F1;
                    margin-top: 0;
                }}
                .badge {{
                    display: inline-block;
                    padding: 3px 8px;
                    border-radius: 12px;
                    font-size: 11px;
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                .Projects {{ background-color: rgba(255,107,107,0.2); color: #FF6B6B; border: 1px solid #FF6B6B; }}
                .Areas {{ background-color: rgba(77,171,247,0.2); color: #4DABF7; border: 1px solid #4DABF7; }}
                .Resources {{ background-color: rgba(81,207,102,0.2); color: #51CF66; border: 1px solid #51CF66; }}
                .Archives {{ background-color: rgba(173,181,189,0.2); color: #ADB5BD; border: 1px solid #ADB5BD; }}
            </style>
        </head>
        <body>
            <div id="mynetwork"></div>
            <div id="detail-panel">
                <div id="select-message">
                    <h3>Inspect a Note</h3>
                    <p style="color: #94A3B8;">Click any node in the network to view its category and summary details.</p>
                </div>
                <div id="note-details" style="display: none;">
                    <h3 id="note-title"></h3>
                    <span id="note-group" class="badge"></span>
                    <p id="note-summary" style="line-height: 1.5; color: #E2E8F0;"></p>
                </div>
            </div>
            
            <script type="text/javascript">
                var nodes = new vis.DataSet({nodes_js});
                var edges = new vis.DataSet({edges_js});
                
                // Group colors
                var colors = {{
                    "Projects": {{ background: '#FF6B6B', border: '#FF5252', highlight: {{ background: '#FF8787', border: '#FF5252' }} }},
                    "Areas": {{ background: '#4DABF7', border: '#339AF0', highlight: {{ background: '#74C0FC', border: '#339AF0' }} }},
                    "Resources": {{ background: '#51CF66', border: '#37B24D', highlight: {{ background: '#69DB7C', border: '#37B24D' }} }},
                    "Archives": {{ background: '#ADB5BD', border: '#868E96', highlight: {{ background: '#CED4DA', border: '#868E96' }} }}
                }};
                
                nodes.forEach(function(node) {{
                    var grp = node.group;
                    if (colors[grp]) {{
                        node.color = colors[grp];
                    }}
                    node.font = {{ color: '#F8FAFC', size: 14 }};
                    nodes.update(node);
                }});
                
                var container = document.getElementById('mynetwork');
                var data = {{
                    nodes: nodes,
                    edges: edges
                }};
                
                var options = {{
                    physics: {{
                        solver: 'barnesHut',
                        barnesHut: {{
                            gravitationalConstant: -3000,
                            centralGravity: 0.3,
                            springLength: 95,
                            springConstant: 0.04,
                            damping: 0.09
                        }}
                    }},
                    edges: {{
                        color: {{
                            color: '#334155',
                            highlight: '#6366F1'
                        }},
                        width: 2
                    }}
                }};
                
                var network = new vis.Network(container, data, options);
                
                network.on("click", function (params) {{
                    if (params.nodes.length > 0) {{
                        var nodeId = params.nodes[0];
                        var node = nodes.get(nodeId);
                        
                        document.getElementById('select-message').style.display = 'none';
                        document.getElementById('note-details').style.display = 'block';
                        document.getElementById('note-title').innerText = node.label;
                        
                        var groupSpan = document.getElementById('note-group');
                        groupSpan.innerText = node.group;
                        groupSpan.className = "badge " + node.group;
                        
                        // Parse title tag to get description details
                        var tempDiv = document.createElement("div");
                        tempDiv.innerHTML = node.title;
                        var summaryText = tempDiv.innerText.split("\\n").slice(2).join("\\n") || "No summary available.";
                        document.getElementById('note-summary').innerText = summaryText;
                    }}
                }});
            </script>
        </body>
        </html>
        """
        st.components.v1.html(html_code, height=600)
    else:
        st.info("No nodes in the knowledge network yet. Capture some items first!")

# ==================== TAB 2: ASK (RAG Q&A) ====================
with tab_ask:
    st.markdown("### Ask Your AI Assistant")
    st.markdown("Search or consult your second brain. Synthesized answers will cite specific source notes.")
    
    query = st.text_input("Enter your question here...", placeholder="What is the architecture plan for Phase 3?")
    
    if query:
        with st.spinner("Synthesizing answer from retrieved context..."):
            answer, sources = rag_query(query, notes)
            st.markdown("#### 💬 Response")
            st.write(answer)
            
            if sources:
                st.markdown("#### 📚 Referenced Notes")
                cols = st.columns(len(sources))
                for i, src in enumerate(sources):
                    with cols[i]:
                        st.markdown(f"""
                        <div class="card">
                            <span class="badge badge-{src['category'].lower()}">{src['category']}</span>
                            <div class="card-title" style="margin-top:5px;">{src['title']}</div>
                            <p style="color:#94A3B8; font-size:0.85rem; line-height:1.4;">{src['summary']}</p>
                        </div>
                        """, unsafe_allow_html=True)

# ==================== TAB 3: CAPTURE (INTAKE PIPELINE) ====================
with tab_capture:
    st.markdown("### Quick Ingestion")
    
    capture_option = st.selectbox("What would you like to capture?", ["Quick Note / Thought", "Web Link / Bookmark", "Local Document File"])
    
    if capture_option == "Quick Note / Thought":
        with st.form("capture_note_form", clear_on_submit=True):
            note_content = st.text_area("Your note content:", height=150, placeholder="E.g., Remind me to review the Streamlit app documentation tomorrow.")
            submit_note = st.form_submit_button("Capture Note")
            if submit_note:
                if note_content.strip():
                    with st.spinner("Processing capture..."):
                        # Run capture CLI logic
                        try:
                            # Run capture script with --note
                            subprocess.run([sys.executable, "src/capture.py", "--note", note_content.strip()], check=True)
                            # Run classification, embeddings & graph pipeline
                            if run_ingestion_pipeline():
                                st.success("Note captured and organized successfully!")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Ingestion error: {e}")
                else:
                    st.warning("Note content cannot be empty.")
                    
    elif capture_option == "Web Link / Bookmark":
        with st.form("capture_link_form", clear_on_submit=True):
            link_url = st.text_input("URL to scrape:", placeholder="https://example.com/guide")
            submit_link = st.form_submit_button("Capture Link")
            if submit_link:
                if link_url.strip():
                    with st.spinner("Scraping page and extracting content..."):
                        try:
                            # Run capture script with --link
                            subprocess.run([sys.executable, "src/capture.py", "--link", link_url.strip()], check=True)
                            # Run classification, embeddings & graph pipeline
                            if run_ingestion_pipeline():
                                st.success("Link captured, parsed, and organized successfully!")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Ingestion error: {e}")
                else:
                    st.warning("Please provide a valid URL.")
                    
    elif capture_option == "Local Document File":
        uploaded_file = st.file_uploader("Upload a text-based document (.txt, .md, .py, .js, .json, .csv):", type=["txt", "md", "py", "js", "json", "csv"])
        if uploaded_file:
            # Save uploaded file to a temporary location to pass to capture script
            temp_dir = "raw/uploads"
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, uploaded_file.name)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            if st.button("Ingest Uploaded File"):
                with st.spinner("Reading file content and classifying..."):
                    try:
                        # Run capture script with --file
                        subprocess.run([sys.executable, "src/capture.py", "--file", temp_path], check=True)
                        # Clean up temp file
                        os.remove(temp_path)
                        # Run pipeline
                        if run_ingestion_pipeline():
                            st.success("File processed, categorized, and embedded successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Ingestion error: {e}")

# ==================== TAB 4: DIRECTORY ====================
with tab_directory:
    st.markdown("### Browse Your Second Brain")
    
    # Filter Controls
    search_q = st.text_input("Search notes by title, tag, or content:", "")
    cat_filter = st.multiselect("Filter by PARA Category:", ["Projects", "Areas", "Resources", "Archives"])
    
    filtered_notes = notes
    if search_q:
        q_lower = search_q.lower()
        filtered_notes = [
            n for n in filtered_notes 
            if q_lower in n["title"].lower() 
            or q_lower in n["body"].lower() 
            or any(q_lower in tag.lower() for tag in n["tags"])
        ]
    if cat_filter:
        filtered_notes = [n for n in filtered_notes if n["category"] in cat_filter]
        
    if filtered_notes:
        for idx, note in enumerate(filtered_notes):
            # Display each note in a clean collapse block
            with st.expander(f"[{note['category'].upper()}] — {note['title']}"):
                st.markdown(f"**Category**: `{note['category']}` | **Tags**: {', '.join(f'`{tag}`' for tag in note['tags']) if note['tags'] else '*None*'}")
                st.markdown(f"**Summary**: *{note['summary']}*")
                st.markdown("---")
                st.write(note["body"])
    else:
        st.info("No matching notes found in the directory.")
