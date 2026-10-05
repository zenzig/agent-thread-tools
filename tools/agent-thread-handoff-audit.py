#!/usr/bin/env python3
"""Check a handoff for items its session shows a fresh session would need (uses Jev)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_thread_tools import jev
from agent_thread_tools.handoff_audit import audit, format_audit, to_json
from agent_thread_tools.sessionlib import expand_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-thread-tools handoff-audit",
        description="List items from a session that a fresh session would need but the handoff "
        "does not state. Uses Jev on OpenRouter; sends redacted text only.",
    )
    parser.add_argument("session_file")
    parser.add_argument("handoff_file")
    parser.add_argument(
        "--previous",
        help="the previous handoff to check for open items (default: the one CLAUDE.local.md points to)",
    )
    parser.add_argument("--no-previous", action="store_true", help="don't check the previous handoff")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)
    if not jev.available():
        print(
            "Handoff audit skipped: no OpenRouter key (run `agent-thread-tools jev-key set`, "
            "or set OPENROUTER_API_KEY)."
        )
        return 0
    try:
        previous = False if args.no_previous else (expand_path(args.previous) if args.previous else None)
        report = audit(expand_path(args.session_file), expand_path(args.handoff_file), previous)
    except jev.JevError as exc:
        print(f"Handoff audit skipped: {exc}")
        return 0
    print(to_json(report) if args.json else format_audit(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
