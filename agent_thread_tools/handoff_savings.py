"""Estimate the tokens each recorded handoff saved.

Every request resends the session's whole context. After a handoff, the new
session sends a small context; without it, the old session would have kept
growing from where it ended. For each request in the replacement session, the
saving is the difference between that counterfactual context (old end + the same
growth) and the context actually sent. Counting stops where the counterfactual
session would have reached auto-compaction, which would have shrunk it anyway, and
at the replacement session's own handoff. The requests spent writing the handoff
are subtracted as overhead.

Cached input costs about a tenth of uncached input, so the report also gives a
price-weighted figure in uncached-token equivalents.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_thread_tools.handoff_markers import session_identity
from agent_thread_tools.sessionlib import iter_jsonl, record_text, session_agent

COMPACTION_SHARE = 0.83
CORRECTION_MIN = 0.7
CORRECTION_QUESTION = {
    "type": "noul",
    "instructions": (
        "Is the user correcting the assistant because it lacked or forgot context from "
        "earlier work: a decision, preference, project state, or fact the user had already given?"
    ),
    "criteria": {
        "true": "The user points out something the assistant should already have known from earlier work.",
        "false": "A new request, new information, feedback on new results, or an ordinary instruction.",
    },
}
WEIGHTS = {"cache_read": 0.1, "cache_write": 1.25, "fresh": 1.0, "output": 5.0}


def session_requests(path: Path) -> list[dict[str, Any]]:
    """One entry per model request: timestamp, context size, and its token mix."""
    if session_agent(path) == "claude":
        return _claude_requests(path)
    return _codex_requests(path)


def _claude_requests(path: Path) -> list[dict[str, Any]]:
    latest: dict[str, tuple[str, dict[str, Any]]] = {}
    order: list[str] = []
    for _line_no, _raw, record in iter_jsonl(path):
        if record.get("type") != "assistant" or record.get("isSidechain"):
            continue
        message = record.get("message")
        if not isinstance(message, dict) or message.get("model") == "<synthetic>":
            continue
        usage, message_id = message.get("usage"), message.get("id")
        if not isinstance(usage, dict) or not isinstance(message_id, str):
            continue
        if message_id not in latest:
            order.append(message_id)
        # A reply is written once per content block; the last copy has the final usage.
        latest[message_id] = (str(record.get("timestamp") or ""), usage)
    requests = []
    for message_id in order:
        timestamp, usage = latest[message_id]
        number = lambda key: usage.get(key) if isinstance(usage.get(key), int) else 0
        read, write, fresh = (
            number("cache_read_input_tokens"),
            number("cache_creation_input_tokens"),
            number("input_tokens"),
        )
        requests.append(
            {
                "timestamp": timestamp,
                "context": read + write + fresh,
                "cache_read": read,
                "cache_write": write,
                "fresh": fresh,
                "output": number("output_tokens"),
            }
        )
    return requests


def _codex_requests(path: Path) -> list[dict[str, Any]]:
    requests = []
    for _line_no, _raw, record in iter_jsonl(path):
        payload = record.get("payload")
        if record.get("type") != "event_msg" or not isinstance(payload, dict):
            continue
        if payload.get("type") != "token_count" or not isinstance(payload.get("info"), dict):
            continue
        usage = payload["info"].get("last_token_usage")
        if not isinstance(usage, dict):
            continue
        number = lambda key: usage.get(key) if isinstance(usage.get(key), int) else 0
        total_input, cached = number("input_tokens"), number("cached_input_tokens")
        requests.append(
            {
                "timestamp": str(record.get("timestamp") or ""),
                "context": total_input,
                "cache_read": cached,
                "cache_write": 0,
                "fresh": max(0, total_input - cached),
                "output": number("output_tokens"),
            }
        )
    return requests


def weighted(requests: list[dict[str, Any]]) -> float:
    return sum(
        WEIGHTS["cache_read"] * item["cache_read"]
        + WEIGHTS["cache_write"] * item["cache_write"]
        + WEIGHTS["fresh"] * item["fresh"]
        + WEIGHTS["output"] * item["output"]
        for item in requests
    )


def compaction_point(requests: list[dict[str, Any]]) -> int:
    largest = max((item["context"] for item in requests), default=0)
    window = 1_000_000 if largest > 200_000 else 200_000
    return int(window * COMPACTION_SHARE)


def handoff_start(path: Path, marker_time: str, asked_at: str | None) -> str:
    """When the handoff turn began: the auto-handoff ask, else the last user prompt before it."""
    if asked_at and asked_at <= marker_time:
        return asked_at
    start = ""
    for _line_no, _raw, record in iter_jsonl(path):
        timestamp = str(record.get("timestamp") or "")
        if not timestamp or timestamp > marker_time:
            continue
        if record.get("type") == "user" and not record.get("isMeta"):
            content = (record.get("message") or {}).get("content")
            is_tool_result = isinstance(content, list) and any(
                isinstance(block, dict) and block.get("type") == "tool_result" for block in content
            )
            if not is_tool_result:
                start = timestamp
        elif record.get("type") in {"event_msg", "response_item"}:
            payload = record.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            # Older Codex logs user_message events; newer ones only user response messages.
            if payload.get("type") == "user_message" or (
                payload.get("type") == "message"
                and payload.get("role") == "user"
                and not record_text(record).lstrip().startswith(("<", "# AGENTS.md"))
            ):
                start = timestamp
    return start or marker_time


def asked_at_for(session_id: str) -> str | None:
    from agent_thread_tools.auto_handoff import state_file

    marker = state_file(session_id)
    try:
        return json.loads(marker.read_text(encoding="utf-8")).get("asked_at")
    except (OSError, ValueError, AttributeError):
        return None


def first_timestamp(requests: list[dict[str, Any]]) -> str:
    return requests[0]["timestamp"] if requests else ""


def auto_handoff_decisions() -> dict[str, list[dict[str, Any]]]:
    """The auto-handoff hook's logged decisions, grouped by session id."""
    from agent_thread_tools.auto_handoff import decisions_file

    grouped: dict[str, list[dict[str, Any]]] = {}
    try:
        lines = decisions_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return grouped
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and isinstance(entry.get("session_id"), str):
            grouped.setdefault(entry["session_id"], []).append(entry)
    return grouped


def project_savings(markers: list[dict[str, Any]], session_paths: list[Path]) -> list[dict[str, Any]]:
    """One row per handoff whose source and replacement sessions are on this machine."""
    decisions = auto_handoff_decisions()
    sessions = []
    for path in session_paths:
        try:
            identity = session_identity(path)
            requests = session_requests(path)
        except (OSError, SystemExit):
            continue
        if requests:
            sessions.append({"path": path, "identity": identity, "requests": requests})
    by_file = {str(item["path"].resolve()): item for item in sessions}
    by_id = {item["identity"]["session_id"]: item for item in sessions}

    rows = []
    for marker in sorted(markers, key=lambda item: item["created_at"]):
        source = by_file.get(str(Path(marker["source_session_file"]).expanduser().resolve())) or by_id.get(
            marker["source_session_id"]
        )
        if source is None:
            continue
        project = source["identity"]["project"]
        later = [
            item
            for item in sessions
            if item is not source
            and item["identity"]["project"] == project
            and first_timestamp(item["requests"]) >= marker["created_at"][:19]
        ]
        if not later:
            continue
        replacement = min(later, key=lambda item: first_timestamp(item["requests"]))
        # Stop at the replacement's own handoff, where the next row takes over.
        own_handoffs = [
            item["created_at"]
            for item in markers
            if item["source_session_id"] == replacement["identity"]["session_id"]
        ]
        stop = min(own_handoffs) if own_handoffs else None
        old_end = source["requests"][-1]["context"]
        base = replacement["requests"][0]["context"]
        limit = compaction_point(source["requests"] + replacement["requests"])
        saved_raw = saved_requests = 0
        saved_mix: list[dict[str, Any]] = []
        for item in replacement["requests"]:
            if stop and item["timestamp"] >= stop:
                break
            counterfactual = old_end + (item["context"] - base)
            if counterfactual > limit:
                break
            saved_raw += counterfactual - item["context"]
            saved_requests += 1
            saved_mix.append(item)
        start = handoff_start(
            source["path"], marker["created_at"], asked_at_for(source["identity"]["session_id"])
        )
        overhead = [
            item
            for item in source["requests"]
            if start[:19] <= item["timestamp"][:19] <= marker["created_at"][:19]
        ]
        overhead_weighted = weighted(overhead) + WEIGHTS["cache_write"] * replacement["requests"][0]["cache_write"]
        corrections = count_corrections(replacement["path"], stop)
        rows.append(
            {
                "project": project,
                "handoff_file": marker["handoff_file"],
                "handoff_at": marker["created_at"],
                "source_session_id": source["identity"]["session_id"],
                "replacement_session_id": replacement["identity"]["session_id"],
                "source_end_context": old_end,
                "replacement_start_context": base,
                "requests_compared": saved_requests,
                "saved_tokens": saved_raw,
                "overhead_requests": len(overhead),
                "overhead_tokens": sum(item["context"] for item in overhead),
                "net_tokens": saved_raw - sum(item["context"] for item in overhead),
                # Context resent on later requests is almost all cache reads.
                "saved_weighted": round(WEIGHTS["cache_read"] * saved_raw),
                "overhead_weighted": round(overhead_weighted),
                "jev_holds": [
                    {"context_tokens": entry.get("context_tokens"), "natural_break": entry.get("natural_break")}
                    for entry in decisions.get(source["identity"]["session_id"], [])
                    if entry.get("decision") == "held"
                ],
                "next_session_prompts": corrections[0],
                "next_session_corrections": corrections[1],
            }
        )
    return rows


def count_corrections(session_file: Path, stop: str | None) -> tuple[int | None, int | None]:
    """Prompts in the session after a handoff, and how many Jev reads as context corrections.

    (None, None) when Jev is not configured or fails.
    """
    from agent_thread_tools import jev
    from agent_thread_tools.handoff_audit import session_items

    if not jev.available():
        return None, None
    prompts = [
        item for item in session_items(session_file)
        if item["role"] == "user" and (not stop or item["timestamp"] < stop)
    ]
    if not prompts:
        return 0, 0
    try:
        answers = jev.decide_many(
            [({"user_prompt": item["text"][:1500]}, {"correction": CORRECTION_QUESTION}) for item in prompts],
            workers=16,
        )
    except Exception:
        return None, None
    flagged = sum(1 for answer in answers if float(answer["answers"]["correction"]["noul"]) >= CORRECTION_MIN)
    return len(prompts), flagged


def savings_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ("saved_tokens", "overhead_tokens", "net_tokens", "saved_weighted", "overhead_weighted")
    summary = {key: sum(row[key] for row in rows) for key in keys}
    summary["handoffs"] = len(rows)
    judged = [row for row in rows if row.get("next_session_prompts") is not None]
    summary["next_session_prompts"] = sum(row["next_session_prompts"] for row in judged) if judged else None
    summary["next_session_corrections"] = sum(row["next_session_corrections"] for row in judged) if judged else None
    summary["net_weighted"] = summary["saved_weighted"] - summary["overhead_weighted"]
    return {"report_type": "handoff_savings", "summary": summary, "handoffs": rows}


def format_savings(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Handoff Savings",
        f"Session folder: {report.get('session_root', '')}",
        f"Handoffs measured: {summary['handoffs']}",
    ]
    if not report["handoffs"]:
        lines.append("No handoff with a later session on this machine was found.")
        return "\n".join(lines)
    lines += [
        f"Tokens not resent: {summary['saved_tokens']:,}",
        f"Handoff overhead: {summary['overhead_tokens']:,}",
        f"Net: {summary['net_tokens']:,} tokens",
        (
            "Price-weighted net (uncached-token equivalents): "
            f"{summary['net_weighted']:,} (saved {summary['saved_weighted']:,}, "
            f"overhead {summary['overhead_weighted']:,})"
        ),
    ]
    if summary.get("next_session_prompts") is not None:
        lines.append(
            "Possible context corrections in the sessions after handoffs (Jev): "
            f"{summary['next_session_corrections']} of {summary['next_session_prompts']} prompts"
        )
    lines.append("")
    for row in report["handoffs"]:
        when = row["handoff_at"][:16].replace("T", " ")
        lines.append(
            f"- {when}  {row['project']}: {row['source_end_context']:,} -> "
            f"{row['replacement_start_context']:,} context; {row['requests_compared']} requests "
            f"compared; saved {row['saved_tokens']:,}, overhead {row['overhead_tokens']:,} "
            f"({row['overhead_requests']} requests)"
            + (
                f"; corrections {row['next_session_corrections']}/{row['next_session_prompts']}"
                if row.get("next_session_prompts") is not None
                else ""
            )
            + (f"; Jev held {len(row['jev_holds'])} turn(s) first" if row.get("jev_holds") else "")
        )
    lines += [
        "",
        "Estimate: assumes the old session would have done the same work, growing from where it",
        "ended, until it reached auto-compaction.",
    ]
    return "\n".join(lines)
