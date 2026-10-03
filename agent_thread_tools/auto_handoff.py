"""Claude Code hooks that hand off a session before its context grows large.

Every request resends the whole conversation, so a session that keeps going at a
large context costs more on every turn. The ``Stop`` hook checks the context size
after each completed turn and, once it passes a threshold, asks Claude to run
``/thread-handoff``. The user then runs ``/clear`` and continues from the handoff.

Hooks must never break a session, so every failure here is silent.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_THRESHOLD = "250k"
# With Jev available, hand off at the first natural break past the threshold, or at
# 1.5 times the threshold regardless.
NATURAL_BREAK_MIN = 0.75
HARD_LIMIT_FACTOR = 1.5
NATURAL_BREAK_QUESTION = {
    "type": "noul",
    "instructions": (
        "Is this a good moment to end this coding session and continue in a fresh "
        "session from a written handoff?"
    ),
    "criteria": {
        "true": (
            "The work just reported is finished and recorded (committed, shipped, or "
            "reported with results), nothing is still running, and the assistant is "
            "waiting on the user or about to start a separate piece of work."
        ),
        "false": (
            "Work is mid-way: something is still running, being tested, uncommitted, or "
            "the assistant is about to continue the same task."
        ),
    },
}
TAIL_BYTES = 4 * 1024 * 1024
DISABLE_ENV = "AGENT_THREAD_AUTO_HANDOFF"


def parse_threshold(value: str) -> tuple[int | None, float | None]:
    """``150k``, ``150000`` or ``1m`` give tokens; ``60%`` gives a share of the window."""
    text = value.strip().lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return None, float(match.group(1)) / 100
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([km]?)", text)
    if not match:
        raise ValueError("threshold must look like 150k, 150000, 1m, or 60%")
    scale = {"": 1, "k": 1_000, "m": 1_000_000}[match.group(2)]
    return int(float(match.group(1)) * scale), None


def latest_context_tokens(transcript: Path) -> int | None:
    """Context size of the latest main-thread reply, read from the end of the file."""
    size = transcript.stat().st_size
    with transcript.open("rb") as handle:
        handle.seek(max(0, size - TAIL_BYTES))
        lines = handle.read().splitlines()
    for raw in reversed(lines):
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict) or record.get("type") != "assistant":
            continue
        if record.get("isSidechain"):
            continue
        message = record.get("message")
        if not isinstance(message, dict) or message.get("model") == "<synthetic>":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        keys = (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        )
        return sum(value for value in (usage.get(key) for key in keys) if isinstance(value, int))
    return None


def context_window(tokens: int) -> int:
    configured = os.environ.get("CLAUDE_CONTEXT_WINDOW", "")
    if configured.isdigit():
        return int(configured)
    return 1_000_000 if tokens > 200_000 else 200_000


def state_file(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id) or "unknown"
    return Path.home() / ".claude" / "thread-tools" / "auto-handoff" / f"{safe}.json"


def stop_decision(event: dict[str, Any], threshold: str) -> dict[str, Any] | None:
    """The hook's JSON reply, or None to let the turn end normally."""
    if os.environ.get(DISABLE_ENV, "").lower() in {"0", "off", "false", "no"}:
        return None
    if event.get("stop_hook_active"):
        return None
    if event.get("background_tasks"):
        # Work is still running; ask after it finishes so the handoff records the result.
        return None
    stop_reason = event.get("stop_reason")
    if stop_reason not in (None, "", "end_turn"):
        return None
    transcript = event.get("transcript_path")
    session_id = str(event.get("session_id") or "")
    if not isinstance(transcript, str) or not session_id:
        return None
    path = Path(transcript).expanduser()
    if not path.is_file():
        return None
    tokens = latest_context_tokens(path)
    if tokens is None:
        return None
    limit, share = parse_threshold(threshold)
    window = context_window(tokens)
    if limit is None:
        limit = int(window * (share or 0))
    if tokens < limit:
        return None
    marker = state_file(session_id)
    if marker.exists():
        return None  # ask once per session; the user may choose to keep going
    natural_break = None
    if tokens < limit * HARD_LIMIT_FACTOR:
        natural_break = natural_break_probability(event)
        if natural_break is not None and natural_break < NATURAL_BREAK_MIN:
            return None  # mid-task; check again after the next turn
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "transcript_path": str(path),
                "context_tokens": tokens,
                "threshold_tokens": limit,
                "natural_break": natural_break,
                "asked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    moment = " and this is a natural break" if natural_break is not None else ""
    return {
        "decision": "block",
        "reason": (
            f"agent-thread-tools auto-handoff: this session's context is about "
            f"{tokens:,} tokens, past the {limit:,}-token threshold{moment}, so every further "
            "request resends that much. Run the /thread-handoff skill now to write the "
            "handoff. When it is done, tell the user in one short paragraph that the "
            "handoff is saved and that running /clear continues from it in a fresh, "
            "smaller session. If the user asked earlier in this session not to hand "
            "off, skip the handoff, say so in one line, and stop."
        ),
    }


def natural_break_probability(event: dict[str, Any]) -> float | None:
    """Jev's probability that the turn just finished is a good place to hand off.

    None when Jev is not configured or fails, so the hook falls back to asking now.
    """
    from agent_thread_tools import jev

    reply = event.get("last_assistant_message")
    if not jev.available() or not isinstance(reply, str) or not reply.strip():
        return None
    state = {"last_reply": reply[-3000:], "background_tasks_running": len(event.get("background_tasks") or [])}
    try:
        answer = jev.decide(state, {"natural_break": NATURAL_BREAK_QUESTION}, timeout=8)
        return float(answer["answers"]["natural_break"]["noul"])
    except Exception:
        return None


def precompact_draft(event: dict[str, Any]) -> Path | None:
    """Save a redacted handoff draft before Claude Code compacts, if the project uses .reference/."""
    from agent_thread_tools.handoff_summary import build_handoff_summary, format_handoff_summary

    transcript = event.get("transcript_path")
    cwd = event.get("cwd")
    if not isinstance(transcript, str) or not isinstance(cwd, str):
        return None
    reference = Path(cwd) / ".reference"
    path = Path(transcript).expanduser()
    if not reference.is_dir() or not path.is_file():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    target = reference / "handoffs" / f"{stamp}-before-compaction-draft.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = format_handoff_summary(build_handoff_summary(path))
    trigger = event.get("trigger") or "unknown"
    target.write_text(
        "# Draft saved before compaction\n\n"
        f"Claude Code compacted this session ({trigger}). This is the redacted summary "
        "agent-thread-tools saved first; it is a draft, not a reviewed handoff.\n\n"
        + summary
        + "\n",
        encoding="utf-8",
    )
    return target
