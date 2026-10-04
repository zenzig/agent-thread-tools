#!/usr/bin/env python3
"""Store, check, or remove the OpenRouter key used for Jev, without ever showing it."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_thread_tools import jev


def read_key(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().strip()
    if not sys.stdin.isatty():
        raise SystemExit(
            "error: run this in a terminal so the key can be typed hidden, or pipe it in with --stdin"
        )
    return getpass.getpass("OpenRouter API key (input hidden): ").strip()


def verify(key: str) -> str:
    """"" when the key works, else the reason it did not."""
    try:
        jev.decide(
            {"check": "agent-thread-tools key check"},
            {"ok": jev.noul("Is this a key check?", "It is a key check.", "It is not.")},
            timeout=20,
            key=key,
        )
    except jev.JevError as exc:
        return str(exc)
    return ""


def set_key(args: argparse.Namespace) -> int:
    key = read_key(args.stdin)
    if not key or any(character.isspace() for character in key):
        print("error: that does not look like an API key (empty or contains spaces); nothing was saved.")
        return 1
    if not key.startswith("sk-or-"):
        print("Note: OpenRouter keys usually start with sk-or-.")
    if not args.no_verify:
        problem = verify(key)
        if problem:
            print(f"error: OpenRouter rejected the key or could not be reached; nothing was saved. ({problem})")
            return 1
    path = jev.store_key(key)
    print(f"Saved {jev.mask(key)} to {path} (readable only by you).")
    if os.environ.get("OPENROUTER_API_KEY"):
        print("Note: OPENROUTER_API_KEY is set in this environment and takes precedence over the file.")
    return 0


def status(args: argparse.Namespace) -> int:
    key, source, problem = jev.key_source()
    if problem:
        print(f"Jev key: not used. {problem}")
        return 1
    if not key:
        print("Jev key: none. Run `agent-thread-tools jev-key set` to add one.")
        return 0
    print(f"Jev key: {jev.mask(key)} from {source}")
    if os.environ.get(jev.DISABLE_ENV, "").lower() in {"0", "off", "false", "no"}:
        print(f"Jev is turned off by {jev.DISABLE_ENV}.")
    if args.verify:
        problem = verify(key)
        print("Check: OK" if not problem else f"Check failed: {problem}")
        return 1 if problem else 0
    return 0


def remove(_args: argparse.Namespace) -> int:
    removed = [path for path in (jev.key_file(), jev.legacy_key_file()) if path.is_file()]
    for path in removed:
        path.unlink()
        print(f"Removed {path}")
    if not removed:
        print("No stored key found.")
    if os.environ.get("OPENROUTER_API_KEY"):
        print("Note: OPENROUTER_API_KEY is still set in this environment.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-thread-tools jev-key",
        description="Manage the OpenRouter API key used for Jev. The key is never printed in full.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    set_parser = sub.add_parser("set", help="prompt for the key (hidden), check it, and store it privately")
    set_parser.add_argument("--stdin", action="store_true", help="read the key from standard input, e.g. from a password manager")
    set_parser.add_argument("--no-verify", action="store_true", help="store without the test call")
    set_parser.set_defaults(func=set_key)
    status_parser = sub.add_parser("status", help="show where the key comes from (masked)")
    status_parser.add_argument("--verify", action="store_true", help="also make one test call")
    status_parser.set_defaults(func=status)
    sub.add_parser("remove", help="delete the stored key").set_defaults(func=remove)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
