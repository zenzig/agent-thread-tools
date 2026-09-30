#!/usr/bin/env python3
"""Claude Code hook commands: read the hook event from stdin, reply on stdout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_thread_tools.auto_handoff import (
    DEFAULT_THRESHOLD,
    parse_threshold,
    precompact_draft,
    stop_decision,
)


def read_event() -> dict:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}
    return event if isinstance(event, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-thread-tools hook",
        description="Claude Code hooks for automatic handoffs. Claude Code runs these; "
        "install them with `agent-thread-tools install-skill --agent claude --auto-handoff`.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    stop = sub.add_parser("claude-stop", help="Stop hook: ask for a handoff past the threshold")
    stop.add_argument(
        "--at",
        default=DEFAULT_THRESHOLD,
        help=f"context size that triggers a handoff, e.g. 150k or 60%% (default {DEFAULT_THRESHOLD})",
    )
    sub.add_parser("claude-precompact", help="PreCompact hook: save a handoff draft first")
    args = parser.parse_args(argv)
    if args.command == "claude-stop":
        parse_threshold(args.at)  # reject a bad threshold at install time, loudly
    event = read_event()
    try:
        if args.command == "claude-stop":
            decision = stop_decision(event, args.at)
            if decision:
                print(json.dumps(decision))
        else:
            precompact_draft(event)
    except Exception:  # a hook must never break the session
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
