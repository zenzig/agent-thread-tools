"""Minimal client for Jev, TypeSafe's decision model on OpenRouter.

Jev does not write text: it answers typed questions about a ``state`` with
probabilities (``noul`` yes/no, ``choice``, ``score``). It is billed on input
tokens only. Everything sent is passed through the tool's redaction first.
"""

from __future__ import annotations

import json
import os
import stat
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from agent_thread_tools.redaction import redact_sensitive_text

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
RETRIES = 3
RETRY_CODES = {429, 500, 502, 503, 504}
RETRY_DELAY = 1.0  # seconds, doubled on each retry


class JevError(RuntimeError):
    pass


DISABLE_ENV = "AGENT_THREAD_JEV"


def key_file() -> Path:
    """Where `agent-thread-tools jev-key set` stores the key."""
    override = os.environ.get("AGENT_THREAD_JEV_KEY_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "agent-thread-tools" / "openrouter-key"


def legacy_key_file() -> Path:
    return Path.home() / ".config" / "openrouter" / "key"


def key_file_problem(path: Path) -> str:
    """Why a key file must not be used, or "" when it is safe (owned by you, private)."""
    if os.name == "nt":
        return ""
    info = path.stat()
    if info.st_uid != os.getuid():
        return f"{path} is not owned by you"
    if stat.S_IMODE(info.st_mode) & 0o077:
        return f"{path} can be read by other users; run: chmod 600 {path}"
    return ""


def key_source() -> tuple[str, str, str]:
    """(key, where it came from, problem). The key is "" when none is usable."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key, "OPENROUTER_API_KEY", ""
    candidates = [key_file()] if os.environ.get("AGENT_THREAD_JEV_KEY_FILE") else [key_file(), legacy_key_file()]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            problem = key_file_problem(path)
            if problem:
                return "", str(path), problem
            return path.read_text(encoding="utf-8").strip(), str(path), ""
        except OSError as exc:
            return "", str(path), f"cannot read {path}: {exc.strerror}"
    return "", "", ""


def api_key() -> str:
    """OPENROUTER_API_KEY, else the stored key file, but never a file others can read."""
    return key_source()[0]


def store_key(key: str) -> Path:
    """Write the key so only the current user can read it, replacing any old one atomically."""
    target = key_file()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(target.parent, 0o700)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(key)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def mask(key: str) -> str:
    return f"{key[:8]}…{key[-4:]}" if len(key) > 16 else "…"


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
    key: str | None = None,
) -> dict[str, Any]:
    """Send one decision request; returns the full response (``answers``, ``usage``)."""
    if key is None:
        key, _source, problem = key_source()
        if not key:
            raise JevError(problem or "no OpenRouter key: run `agent-thread-tools jev-key set`")
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
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            # Rate limits and server errors pass; wait and try again before giving up.
            if getattr(exc, "code", None) in RETRY_CODES and attempt < RETRIES:
                time.sleep(RETRY_DELAY * 2**attempt)
                continue
            detail = getattr(exc, "read", lambda: b"")()
            raise JevError(f"Jev request failed: {exc} {detail[:300]!r}") from exc
    raise JevError("Jev request failed")


def decide_many(
    requests: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]],
    *,
    workers: int = 8,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """Run independent decision requests in parallel, keeping their order."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda item: decide(item[0], item[1], timeout=timeout), requests))
