"""Minimal client for Jev, TypeSafe's decision model on OpenRouter.

Jev does not write text: it answers typed questions about a ``state`` with
probabilities (``noul`` yes/no, ``choice``, ``score``). It is billed on input
tokens only. Everything sent is passed through the tool's redaction first.
"""

from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from agent_thread_tools.redaction import redact_sensitive_text

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"


class JevError(RuntimeError):
    pass


DISABLE_ENV = "AGENT_THREAD_JEV"


def api_key() -> str:
    """OPENROUTER_API_KEY, else the key file (default ~/.config/openrouter/key)."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    key_file = Path(
        os.environ.get("AGENT_THREAD_JEV_KEY_FILE") or Path.home() / ".config" / "openrouter" / "key"
    ).expanduser()
    try:
        return key_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def available() -> bool:
    if os.environ.get(DISABLE_ENV, "").lower() in {"0", "off", "false", "no"}:
        return False
    return bool(api_key())


def redact_state(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)[0]
    if isinstance(value, dict):
        return {key: redact_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_state(item) for item in value]
    return value


def noul(instructions: str, yes: str, no: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": instructions, "criteria": {"true": yes, "false": no}}


def decide(
    state: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Send one decision request; returns the full response (``answers``, ``usage``)."""
    key = api_key()
    if not key:
        raise JevError("no OpenRouter key: set OPENROUTER_API_KEY or save it to ~/.config/openrouter/key")
    body = json.dumps(
        {
            "model": os.environ.get("AGENT_THREAD_JEV_MODEL", DEFAULT_MODEL),
            "state": redact_state(state),
            "questions": questions,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        detail = getattr(exc, "read", lambda: b"")()
        raise JevError(f"Jev request failed: {exc} {detail[:300]!r}") from exc


def decide_many(
    requests: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]],
    *,
    workers: int = 8,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """Run independent decision requests in parallel, keeping their order."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda item: decide(item[0], item[1], timeout=timeout), requests))
