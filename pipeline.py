#!/usr/bin/env python3
"""Orchestrate classify + link + graph pipelines."""

from __future__ import annotations

import argparse
import sys


def cmd_classify(force: bool = False) -> int:
    from classify import classify_all
    from lib.llm import LLMError

    try:
        classify_all(force=force)
    except LLMError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_link(threshold: float = 0.55, force: bool = False) -> int:
    from lib.embeddings import EmbeddingError
    from link import link_notes

    try:
        link_notes(threshold=threshold, force=force)
    except EmbeddingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_graph() -> int:
    from build_graph import build_graph

    try:
        build_graph()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_process(threshold: float = 0.55, force: bool = False) -> int:
    print("=== Classify ===")
    rc = cmd_classify(force=force)
    if rc != 0:
        return rc
    print("\n=== Link ===")
    rc = cmd_link(threshold=threshold, force=force)
    if rc != 0:
        return rc
    print("\n=== Graph ===")
    return cmd_graph()


def process(threshold: float = 0.55, force: bool = False) -> int:
    """Programmatic entry point for the Streamlit app / callers."""
    return cmd_process(threshold=threshold, force=force)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SecondSelf pipeline: classify, link, and/or build graph",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    classify_p = sub.add_parser("classify", help="Classify unprocessed raw captures")
    classify_p.add_argument(
        "--force",
        action="store_true",
        help="Re-classify all raw captures",
    )

    link_p = sub.add_parser("link", help="Embed and auto-link wiki notes")
    link_p.add_argument(
        "--threshold",
        type=float,
        default=0.55,
        help="Cosine similarity threshold (default 0.55)",
    )
    link_p.add_argument(
        "--force",
        action="store_true",
        help="Re-embed all notes",
    )

    sub.add_parser("graph", help="Build data/graph.json from wiki notes")

    process_p = sub.add_parser("process", help="Classify, link, then build graph")
    process_p.add_argument(
        "--threshold",
        type=float,
        default=0.55,
        help="Cosine similarity threshold (default 0.55)",
    )
    process_p.add_argument(
        "--force",
        action="store_true",
        help="Force re-classify and re-embed",
    )

    args = parser.parse_args(argv)

    if args.command == "classify":
        return cmd_classify(force=args.force)
    if args.command == "link":
        return cmd_link(threshold=args.threshold, force=args.force)
    if args.command == "graph":
        return cmd_graph()
    if args.command == "process":
        return cmd_process(threshold=args.threshold, force=args.force)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
