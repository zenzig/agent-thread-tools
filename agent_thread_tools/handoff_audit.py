"""Check a written handoff against the session it came from, using Jev.

Every prompt the user typed and the closing message of each assistant turn is a
candidate item. Jev answers two questions per item: would a fresh session need it,
and does the handoff already state it? Items that are needed but missing are
listed for the assistant to review.

The new handoff replaces the previous one, so the open items of the previous
handoff (owed checks, pending decisions, proposals, risks) are checked too: any the
new handoff doesn't state are listed as not carried forward. Only redacted text is
sent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_thread_tools import jev
from agent_thread_tools.sessionlib import iter_jsonl, payload_role, payload_type, record_text, session_agent

NEEDED_MIN = 0.7
SUBSTANTIAL_CHARS = 120  # mid-turn assistant messages at least this long are checked too
ITEM_LIMIT = 300
REFLECTED_MAX = 0.3
PREVIOUS_ITEM_LIMIT = 60
OPEN_SECTION = re.compile(r"next action|open question|risk|still open|owed|pending|waiting", re.IGNORECASE)
OPEN_WORDS = re.compile(
    r"\b(owed|pending|awaiting|waiting (on|for)|needs? .{0,40}\byes\b|proposed|not run|unverified|still open|todo)\b",
    re.IGNORECASE,
)
# Sections that record state, not open work; their "awaiting" or "not run" lines are history.
STATE_SECTION = re.compile(r"resume context|verification|files|references|source session|visual archive", re.IGNORECASE)
LATEST_HANDOFF = re.compile(r"Latest handoff:\s*@(\S+)")
SKIPPED_PREFIXES = ("<", "Stop hook", "Base directory", "[Request")
CODEX_SKIPPED_PREFIXES = ("<", "# AGENTS.md")  # environment context and instruction files

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
    """User and assistant messages from a Codex rollout, up to the handoff request.

    Newer Codex versions record messages only as ``response_item`` messages; older
    ones also log ``event_msg`` copies, which are skipped when they repeat.
    """
    items: list[dict[str, str]] = []
    for _line_no, _raw, record in iter_jsonl(path):
        rtype, ptype = record.get("type"), payload_type(record)
        if rtype == "response_item" and ptype == "message":
            role = payload_role(record)
        elif rtype == "event_msg":
            role = {"user_message": "user", "agent_message": "assistant"}.get(ptype, "")
        else:
            continue
        if role not in {"user", "assistant"}:
            continue  # developer and system instructions
        text = record_text(record).strip()
        if not text or text.startswith(CODEX_SKIPPED_PREFIXES):
            continue
        if role == "user" and "codex-thread-handoff" in text:
            break
        if items and items[-1]["role"] == role and items[-1]["text"] == text:
            continue
        items.append({"role": role, "timestamp": str(record.get("timestamp") or ""), "text": text})
    return items[-ITEM_LIMIT:]


def previous_handoff(handoff_file: Path) -> Path | None:
    """The handoff that `CLAUDE.local.md` still points to, if it isn't this one."""
    resolved = handoff_file.resolve()
    for folder in resolved.parents:
        if folder.name == ".reference":
            local = folder.parent / "CLAUDE.local.md"
            try:
                match = LATEST_HANDOFF.search(local.read_text(encoding="utf-8"))
            except OSError:
                return None
            if not match:
                return None
            previous = (folder.parent / match.group(1)).resolve()
            return previous if previous != resolved and previous.is_file() else None
    return None


def open_items(text: str) -> list[str]:
    """Bullets and paragraphs of a handoff that record something still open."""
    items: list[str] = []
    heading, buffer, bullet = "", [], False

    def flush() -> None:
        if buffer and not STATE_SECTION.search(heading):
            item = " ".join(buffer)
            if OPEN_SECTION.search(heading) or OPEN_WORDS.search(item) or item.startswith(("Current:", "Next:")):
                items.append(item)
        buffer.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if line.startswith("#"):
            flush()
            heading = line
            continue
        if not stripped:
            flush()
            continue
        starts_bullet = re.match(r"^\s*([-*]|\d+[.)])\s+", line) is not None
        if starts_bullet:
            flush()
            buffer.append(stripped)
            bullet = True
        elif buffer and (line[:1].isspace() or not bullet):
            buffer.append(stripped)
        else:
            flush()
            buffer.append(stripped)
            bullet = False
    flush()
    return [item[:1500] for item in items[:PREVIOUS_ITEM_LIMIT]]


def audit(session_file: Path, handoff_file: Path, previous_file: Path | None | bool = None) -> dict[str, Any]:
    """Audit a handoff. ``previous_file`` None finds the previous handoff; False skips it."""
    handoff = handoff_file.read_text(encoding="utf-8")
    items = session_items(session_file)
    if previous_file is None:
        previous_file = previous_handoff(handoff_file)
    previous = open_items(previous_file.read_text(encoding="utf-8")) if previous_file else []
    requests = [
        ({"handoff": handoff, "item_role": item["role"], "item": item["text"][:1500]}, {"needed": NEEDED, "reflected": REFLECTED})
        for item in items
    ] + [
        ({"handoff": handoff, "item_role": "open item from the previous handoff", "item": text}, {"reflected": REFLECTED})
        for text in previous
    ]
    answers = jev.decide_many(requests)
    cost = sum(float((response.get("usage") or {}).get("cost") or 0) for response in answers)
    scored = []
    for item, response in zip(items, answers):
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
    not_carried = [
        {"text": text, "reflected": float(response["answers"]["reflected"]["noul"])}
        for text, response in zip(previous, answers[len(items):])
        if float(response["answers"]["reflected"]["noul"]) <= REFLECTED_MAX
    ]
    return {
        "report_type": "handoff_audit",
        "session_file": str(session_file),
        "handoff_file": str(handoff_file),
        "items_checked": len(scored),
        "possibly_missing": missing,
        "previous_handoff": str(previous_file) if previous_file else "",
        "previous_items_checked": len(previous),
        "not_carried_forward": not_carried,
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
        lines.append("Nothing needed from this session appears to be missing.")
    else:
        lines.append(f"Possibly missing ({len(missing)}): check each; add it to the handoff if it still applies.")
        for item in missing:
            text = " ".join(item["text"].split())[:300]
            lines.append(f"- [{item['role']} {item['timestamp'][:16]}] {text}")
    if report.get("previous_handoff"):
        name = Path(report["previous_handoff"]).name
        carried = report["not_carried_forward"]
        if not carried:
            lines.append(f"Open items from the previous handoff ({name}, {report['previous_items_checked']} checked) are carried forward.")
        else:
            lines.append(
                f"Not carried forward from the previous handoff ({name}), {len(carried)} of "
                f"{report['previous_items_checked']}: if one is still open, add it to the new handoff."
            )
            for item in carried:
                text = re.sub(r"^[-*]\s+", "", " ".join(item["text"].split()))
                lines.append(f"- {text[:300]}")
    return "\n".join(lines)


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2)
