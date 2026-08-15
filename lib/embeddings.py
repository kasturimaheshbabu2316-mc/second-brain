"""Local embedding helpers via sentence-transformers."""

from __future__ import annotations

import pickle
import shutil
import sys
from pathlib import Path

import numpy as np

from lib.storage import DATA_DIR, ensure_dirs

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.pkl"
EMBEDDING_DIM = 384

_model = None


class EmbeddingError(Exception):
    """Raised when the embedding model cannot be loaded or used."""


def load_model():
    """Load and cache the sentence-transformers model."""
    global _model
    if _model is not None:
        return _model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingError(
            "sentence-transformers is not installed. "
            "Run: pip install -r requirements.txt"
        ) from exc

    try:
        print(f"Loading embedding model ({MODEL_NAME})...", file=sys.stderr)
        _model = SentenceTransformer(MODEL_NAME)
    except Exception as exc:
        raise EmbeddingError(
            f"Failed to load embedding model '{MODEL_NAME}'. "
            "Check your network connection (first run downloads ~80MB) "
            f"or install it manually.\nDetails: {exc}"
        ) from exc

    return _model


def embed_text(text: str) -> np.ndarray:
    """Return a 384-dim float32 embedding vector for text."""
    model = load_model()
    cleaned = (text or "").strip()
    if not cleaned:
        cleaned = " "

    vector = model.encode(cleaned, convert_to_numpy=True, normalize_embeddings=False)
    arr = np.asarray(vector, dtype=np.float32).reshape(-1)

    if arr.shape != (EMBEDDING_DIM,):
        raise EmbeddingError(
            f"Unexpected embedding shape {arr.shape}; expected ({EMBEDDING_DIM},)"
        )

    if not np.any(arr):
        print("Warning: embedding vector is all zeros", file=sys.stderr)

    return arr


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    b = np.asarray(b, dtype=np.float64).reshape(-1)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def load_embeddings() -> dict[str, np.ndarray]:
    """
    Load note_id → vector map from data/embeddings.pkl.

    Missing file → {}. Corrupt file → backed up as .bak and return {}.
    """
    ensure_dirs()
    if not EMBEDDINGS_PATH.is_file():
        return {}

    try:
        with EMBEDDINGS_PATH.open("rb") as fh:
            data = pickle.load(fh)
    except Exception as exc:  # noqa: BLE001
        bak = EMBEDDINGS_PATH.with_suffix(".pkl.bak")
        try:
            shutil.copy2(EMBEDDINGS_PATH, bak)
            print(
                f"Warning: corrupt embeddings.pkl — backed up to {bak.name} ({exc})",
                file=sys.stderr,
            )
        except OSError:
            print(
                f"Warning: corrupt embeddings.pkl and backup failed ({exc})",
                file=sys.stderr,
            )
        return {}

    if not isinstance(data, dict):
        bak = EMBEDDINGS_PATH.with_suffix(".pkl.bak")
        try:
            shutil.copy2(EMBEDDINGS_PATH, bak)
        except OSError:
            pass
        print("Warning: embeddings.pkl has wrong format — treating as empty", file=sys.stderr)
        return {}

    result: dict[str, np.ndarray] = {}
    for note_id, vector in data.items():
        try:
            result[str(note_id)] = np.asarray(vector, dtype=np.float32).reshape(-1)
        except Exception:  # noqa: S112, BLE001
            continue
    return result


def save_embeddings(embeddings: dict[str, np.ndarray]) -> Path:
    """Atomically write data/embeddings.pkl."""
    ensure_dirs()
    tmp_path = EMBEDDINGS_PATH.with_suffix(".pkl.tmp")
    serializable = {
        note_id: np.asarray(vector, dtype=np.float32)
        for note_id, vector in embeddings.items()
    }
    with tmp_path.open("wb") as fh:
        pickle.dump(serializable, fh, protocol=pickle.HIGHEST_PROTOCOL)
    tmp_path.replace(EMBEDDINGS_PATH)
    return EMBEDDINGS_PATH


def prune_embeddings(
    embeddings: dict[str, np.ndarray],
    valid_ids: set[str],
) -> dict[str, np.ndarray]:
    """Drop orphan embeddings whose notes no longer exist."""
    return {note_id: vec for note_id, vec in embeddings.items() if note_id in valid_ids}
