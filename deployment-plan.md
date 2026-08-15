# Deployment Plan: Streamlit Community Cloud

This document outlines the step-by-step process for deploying the **SecondSelf — Your AI Second Brain** application to **Streamlit Community Cloud**.

---

## 📋 Prerequisites

Before proceeding, ensure you have:

1. A **GitHub account** with the project repository pushed to a public or private repository.
2. A **Streamlit Community Cloud** account (sign up at [share.streamlit.io](https://share.streamlit.io/) using your GitHub account).
3. A **Google Gemini API Key** (retrieve one from [Google AI Studio](https://aistudio.google.com/)).

---

## 🚀 Step-by-Step Deployment

### Step 1: Prepare the Repository

Ensure that the repository contains the correct folder structure:

* `src/app.py`: Main entrypoint for the Streamlit application.
* `requirements.txt`: Python package dependencies.
* `.streamlit/config.toml`: Custom theme and server configurations (for dark mode).
* `data/` and `wiki/` directories: Ensure any template or default data files are committed if required for the initial setup.

### Step 2: Deploy on Streamlit Community Cloud

1. Log in to [Streamlit Community Cloud](https://share.streamlit.io/).
2. Click the **"New app"** button in the top right corner.
3. Configure the deployment settings:
   * **Repository**: Select your GitHub repository (e.g., `username/second-brain`).
   * **Branch**: Select your main branch (e.g., `main` or `master`).
   * **Main file path**: Set this to `src/app.py`.
4. Click **"Advanced settings..."** before deploying.

### Step 3: Configure Environment Secrets

In the **Advanced settings** modal, navigate to the **Secrets** section and add your Gemini API Key in TOML format:

```toml
GEMINI_API_KEY = "your_gemini_api_key_here"
```

> [!IMPORTANT]
> Do not commit the local `.env` file containing your actual API key to GitHub. Streamlit will securely inject this secret into the app environment at runtime.

1. Click **"Save"** and then click **"Deploy!"**.

---

## 🛠️ Performance & Resource Considerations

### 🧠 Embeddings Model Memory Usage

The app imports `sentence-transformers` to generate embeddings locally:

```python
from sentence_transformers import SentenceTransformer
```

* **Memory Limits**: Streamlit Community Cloud provides **1 GB of RAM** per app.
* **Optimization**: The default model used by `sentence-transformers` is usually small, but if you encounter memory issues (e.g., app crash due to `OverMemoryLimit`), consider using a lightweight model like `all-MiniLM-L6-v2` or outsourcing embeddings generation to the Gemini Embeddings API to keep the container lightweight.

### 💾 Data Persistence

* **State Limitation**: Streamlit Community Cloud containers are **ephemeral**. Any changes written to local disk (like updates to `graph.json` or files under `wiki/`) will be lost when the application restarts or goes to sleep.
* **Recommendation**: For persistent note-taking and knowledge graph updates, integrate a cloud database (e.g., Supabase, Firebase, or GitHub API commit-back) rather than saving files directly to local directories.
