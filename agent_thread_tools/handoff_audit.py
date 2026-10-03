"""Check a written handoff against the session it came from, using Jev.

Every prompt the user typed and the closing message of each assistant turn is a
candidate item. Jev answers two questions per item: would a fresh session need it,
and does the handoff already state it? Items that are needed but missing are
listed for the assistant to review. Only redacted text is sent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_thread_tools import jev
from agent_thread_tools.sessionlib import iter_jsonl, session_agent

NEEDED_MIN = 0.7
SUBSTANTIAL_CHARS = 120  # mid-turn assistant messages at least this long are checked too
ITEM_LIMIT = 300
REFLECTED_MAX = 0.3
SKIPPED_PREFIXES = ("<", "Stop hook", "Base directory", "[Request")

NEEDED = jev.noul(
    "Would a fresh coding session that continues this project need this item to work correctly?",
    "It records a decision, instruction, preference, current state, open problem, or next step that still applies.",
    "It is chatter, a progress update that was later superseded, or detail the next session will not need.",
)
REFLECTED = jev.noul(
    "Is the substance of this item already stated in the handoff?",
    "The handoff states this information, possibly in different words.",
    "The handoff does not contain this information.",
)


def session_items(path: Path) -> list[dict[str, str]]:
    """User prompts and assistant messages worth keeping, up to where the handoff began.

    Besides each turn's closing message, substantial messages from the middle of a
    turn count: in a long autonomous turn ("proceed"), that is where the work is
    reported.
    """
    if session_agent(path) == "codex":
        return _codex_items(path)
    items: list[dict[str, str]] = []
    last_text, last_time = "", ""
    for _line_no, _raw, record in iter_jsonl(path):
        message = record.get("message") or {}
        content = message.get("content")
        if record.get("type") == "user" and isinstance(content, str) and content.startswith("Stop hook feedback") and "auto-handoff" in content:
            break
        if record.get("type") == "assistant" and isinstance(content, list):
            if any(
                isinstance(block, dict) and block.get("type") == "tool_use" and "thread-handoff" in str((block.get("input") or {}).get("skill", ""))
                for block in content
            ):
                break
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block["text"].strip():
                    if last_text and len(last_text) >= SUBSTANTIAL_CHARS:
                        items.append({"role": "assistant", "timestamp": last_time, "text": last_text})
                    last_text, last_time = block["text"], str(record.get("timestamp") or "")
        if record.get("type") != "user" or record.get("isMeta"):
            continue
        text = content if isinstance(content, str) else " ".join(
            block.get("text", "") for block in content or [] if isinstance(block, dict) and block.get("type") == "text"
        )
        if not text.strip() or text.startswith(SKIPPED_PREFIXES):
            continue
        if last_text:
            items.append({"role": "assistant", "timestamp": last_time, "text": last_text})
            last_text = ""
        items.append({"role": "user", "timestamp": str(record.get("timestamp") or ""), "text": text})
    if last_text:
        items.append({"role": "assistant", "timestamp": last_time, "text": last_text})
    return items[-ITEM_LIMIT:]


def _codex_items(path: Path) -> list[dict[str, str]]:
    items = []
    for _line_no, _raw, record in iter_jsonl(path):
        payload = record.get("payload")
        if record.get("type") != "event_msg" or not isinstance(payload, dict):
            continue
        role = {"user_message": "user", "agent_message": "assistant"}.get(payload.get("type"))
        text = payload.get("message")
        if role and isinstance(text, str) and text.strip():
            if "codex-thread-handoff" in text:
                break
            items.append({"role": role, "timestamp": str(record.get("timestamp") or ""), "text": text})
    return items


def audit(session_file: Path, handoff_file: Path) -> dict[str, Any]:
    handoff = handoff_file.read_text(encoding="utf-8")
    items = session_items(session_file)
    requests = [
        ({"handoff": handoff, "item_role": item["role"], "item": item["text"][:1500]}, {"needed": NEEDED, "reflected": REFLECTED})
        for item in items
    ]
    answers = jev.decide_many(requests)
    cost = 0.0
    scored = []
    for item, response in zip(items, answers):
        cost += float((response.get("usage") or {}).get("cost") or 0)
        result = response["answers"]
        scored.append(
            {
                **item,
                "needed": float(result["needed"]["noul"]),
                "reflected": float(result["reflected"]["noul"]),
            }
        )
    missing = sorted(
        (item for item in scored if item["needed"] >= NEEDED_MIN and item["reflected"] <= REFLECTED_MAX),
        key=lambda item: -item["needed"],
    )
    return {
        "report_type": "handoff_audit",
        "session_file": str(session_file),
        "handoff_file": str(handoff_file),
        "items_checked": len(scored),
        "possibly_missing": missing,
        "cost_usd": round(cost, 6),
    }


def format_audit(report: dict[str, Any]) -> str:
    lines = [
        "Handoff Audit",
        f"Handoff: {report['handoff_file']}",
        f"Items checked: {report['items_checked']} (cost ${report['cost_usd']:.4f})",
    ]
    missing = report["possibly_missing"]
    if not missing:
        lines.append("Nothing needed appears to be missing.")
        return "\n".join(lines)
    lines.append(f"Possibly missing ({len(missing)}): check each; add it to the handoff if it still applies.")
    for item in missing:
        text = " ".join(item["text"].split())[:300]
        lines.append(f"- [{item['role']} {item['timestamp'][:16]}] {text}")
    return "\n".join(lines)


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2)
