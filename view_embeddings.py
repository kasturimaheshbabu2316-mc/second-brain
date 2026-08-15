#!/usr/bin/env python3
"""Inspect note embeddings stored in data/embeddings.pkl."""

from __future__ import annotations

import argparse
import sys

import numpy as np

from lib.embeddings import EMBEDDING_DIM, EMBEDDINGS_PATH, load_embeddings


def _format_preview(vec: np.ndarray, n: int = 6) -> str:
    head = ", ".join(f"{x:.4f}" for x in vec[:n])
    if len(vec) > n:
        return f"[{head}, ...]"
    return f"[{head}]"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show embeddings from data/embeddings.pkl"
    )
    parser.add_argument(
        "--id",
        metavar="NOTE_ID",
        help="Show the full vector for a single note id",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print every dimension for each note (very long)",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=6,
        metavar="N",
        help="Number of leading dimensions to preview (default: 6)",
    )
    args = parser.parse_args()

    embeddings = load_embeddings()
    if not embeddings:
        print(f"No embeddings found at {EMBEDDINGS_PATH}", file=sys.stderr)
        return 1

    dims = {tuple(v.shape) for v in embeddings.values()}
    dtypes = {str(v.dtype) for v in embeddings.values()}

    print(f"File:      {EMBEDDINGS_PATH}")
    print(f"Notes:     {len(embeddings)}")
    print(f"Shapes:    {', '.join(str(s) for s in sorted(dims))}")
    print(f"Dtypes:    {', '.join(sorted(dtypes))}")
    print(f"Expected:  ({EMBEDDING_DIM},) float32")
    print()

    if args.id:
        note_id = args.id
        if note_id not in embeddings:
            print(f"Note id not found: {note_id}", file=sys.stderr)
            print(f"Available: {', '.join(sorted(embeddings))}", file=sys.stderr)
            return 1
        vec = embeddings[note_id]
        print(f"note_id:   {note_id}")
        print(f"shape:     {vec.shape}")
        print(f"dtype:     {vec.dtype}")
        print(f"L2 norm:   {float(np.linalg.norm(vec)):.6f}")
        print(f"min/max:   {float(vec.min()):.6f} / {float(vec.max()):.6f}")
        print(f"mean:      {float(vec.mean()):.6f}")
        print("vector:")
        np.set_printoptions(precision=6, suppress=True, linewidth=100, threshold=sys.maxsize)
        print(vec)
        return 0

    # Summary table for all notes
    print(f"{'note_id':<12} {'dim':>5} {'norm':>10} {'min':>10} {'max':>10}  preview")
    print("-" * 90)
    for note_id in sorted(embeddings):
        vec = embeddings[note_id]
        norm = float(np.linalg.norm(vec))
        preview = _format_preview(vec, args.preview)
        print(
            f"{note_id:<12} {len(vec):>5} {norm:>10.4f} "
            f"{float(vec.min()):>10.4f} {float(vec.max()):>10.4f}  {preview}"
        )
        if args.full:
            np.set_printoptions(
                precision=6, suppress=True, linewidth=100, threshold=sys.maxsize
            )
            print(vec)
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
