"""Deployment helpers for Streamlit Community Cloud."""

from __future__ import annotations

import os
from pathlib import Path

from lib.storage import PROJECT_ROOT

# Streamlit Cloud mounts the repo at /mount/src
_STREAMLIT_CLOUD_ROOT = Path("/mount/src")


def is_streamlit_cloud() -> bool:
    """True when running on Streamlit Community Cloud."""
    try:
        return _STREAMLIT_CLOUD_ROOT.is_dir() and PROJECT_ROOT.resolve().is_relative_to(
            _STREAMLIT_CLOUD_ROOT
        )
    except (ValueError, OSError):
        return _STREAMLIT_CLOUD_ROOT.is_dir()


def inject_streamlit_secrets() -> None:
    """
    Copy Streamlit Cloud secrets into os.environ for lib/* modules.

    Local dev uses .env via python-dotenv; Cloud uses the dashboard Secrets UI.
    """
    try:
        import streamlit as st
    except ImportError:
        return

    try:
        secrets = st.secrets
    except Exception:
        return

    for key in ("GROQ_API_KEY",):
        if os.getenv(key, "").strip():
            continue
        try:
            value = str(secrets[key]).strip()
        except Exception:
            continue
        if value and value != "your_key_here":
            os.environ[key] = value
