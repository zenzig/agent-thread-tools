from __future__ import annotations

import json
from pathlib import Path

from agent_thread_tools.handoff_savings import project_savings, savings_report, session_requests


def claude_session(path: Path, session_id: str, contexts: list[tuple[str, int]]) -> Path:
    records = [
        {
            "type": "user",
            "sessionId": session_id,
            "cwd": "/work/project",
            "timestamp": contexts[0][0],
            "message": {"role": "user", "content": "go"},
        }
    ]
    for index, (timestamp, context) in enumerate(contexts):
        usage = {
            "input_tokens": 10,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": context - 10,
            "output_tokens": 100,
        }
        message = {"id": f"m{index}", "model": "claude-opus-5-5", "usage": usage, "content": []}
        # Claude Code writes one record per content block; both carry the same message id.
        records.append({"type": "assistant", "sessionId": session_id, "timestamp": timestamp, "message": message})
        records.append({"type": "assistant", "sessionId": session_id, "timestamp": timestamp, "message": message})
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    return path


def marker(source: Path, session_id: str, created_at: str) -> dict:
    return {
        "type": "handoff_completed",
        "created_at": created_at,
        "project": "/work/project",
        "source_session_id": session_id,
        "source_session_file": str(source),
        "handoff_file": "/work/project/.reference/handoffs/h.md",
        "handoff_sequence": 1,
    }


def test_requests_are_counted_once_per_reply(tmp_path: Path) -> None:
    path = claude_session(tmp_path / "a.jsonl", "a", [("2026-10-01T10:00:00Z", 1000), ("2026-10-01T10:01:00Z", 2000)])
    assert [item["context"] for item in session_requests(path)] == [1000, 2000]


def test_saving_is_the_old_size_carried_forward(tmp_path: Path) -> None:
    old = claude_session(
        tmp_path / "old.jsonl",
        "old",
        [("2026-10-01T10:00:00Z", 300_000), ("2026-10-01T11:00:00Z", 400_000), ("2026-10-01T11:01:00Z", 410_000)],
    )
    claude_session(
        tmp_path / "new.jsonl",
        "new",
        [("2026-10-01T12:00:00Z", 50_000), ("2026-10-01T12:05:00Z", 60_000), ("2026-10-01T12:10:00Z", 70_000)],
    )
    rows = project_savings([marker(old, "old", "2026-10-01T11:01:30Z")], [old, tmp_path / "new.jsonl"])
    [row] = rows
    assert row["requests_compared"] == 3
    assert row["saved_tokens"] == 3 * (410_000 - 50_000)
    # The handoff turn: the last user prompt was at 10:00, so all three old requests count.
    assert row["overhead_requests"] == 3
    report = savings_report(rows)
    assert report["summary"]["net_tokens"] == row["saved_tokens"] - row["overhead_tokens"]


def test_counting_stops_where_the_old_session_would_have_compacted(tmp_path: Path) -> None:
    old = claude_session(tmp_path / "old.jsonl", "old", [("2026-10-01T11:00:00Z", 800_000)])
    claude_session(
        tmp_path / "new.jsonl",
        "new",
        [("2026-10-01T12:00:00Z", 50_000), ("2026-10-01T12:05:00Z", 60_000), ("2026-10-01T12:10:00Z", 90_000)],
    )
    [row] = project_savings([marker(old, "old", "2026-10-01T11:01:00Z")], [old, tmp_path / "new.jsonl"])
    # 800k + 10k growth stays under 830k; 800k + 40k would have compacted.
    assert row["requests_compared"] == 2


def test_codex_sessions_use_token_count_events(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    records = [
        {"type": "session_meta", "timestamp": "2026-10-01T10:00:00Z", "payload": {"id": "c1", "cwd": "/work/project"}},
        {
            "type": "event_msg",
            "timestamp": "2026-10-01T10:01:00Z",
            "payload": {
                "type": "token_count",
                "info": {"last_token_usage": {"input_tokens": 120_000, "cached_input_tokens": 100_000, "output_tokens": 500}},
            },
        },
    ]
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    [request] = session_requests(path)
    assert request["context"] == 120_000
    assert request["cache_read"] == 100_000 and request["fresh"] == 20_000


def test_corrections_are_counted_when_jev_is_available(tmp_path, monkeypatch) -> None:
    from agent_thread_tools import handoff_savings, jev

    session = tmp_path / "new.jsonl"
    records = [
        {"type": "user", "sessionId": "new", "cwd": "/work/project", "timestamp": "2026-10-01T12:00:00Z", "message": {"role": "user", "content": text}}
        for text in ("Add the login page.", "We already decided to use Postgres, remember?")
    ]
    session.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    monkeypatch.setattr(jev, "available", lambda: True)
    monkeypatch.setattr(
        jev,
        "decide_many",
        lambda requests, **_: [
            {"answers": {"correction": {"noul": 0.9 if "already decided" in state["user_prompt"] else 0.1}}}
            for state, _ in requests
        ],
    )
    assert handoff_savings.count_corrections(session, None) == (2, 1)
    monkeypatch.setattr(jev, "available", lambda: False)
    assert handoff_savings.count_corrections(session, None) == (None, None)


def test_logged_jev_holds_are_read_by_session(tmp_path, monkeypatch) -> None:
    from agent_thread_tools import auto_handoff, handoff_savings

    monkeypatch.setenv("HOME", str(tmp_path))
    auto_handoff.log_decision("s1", 310_000, 300_000, 0.1, "held")
    auto_handoff.log_decision("s1", 330_000, 300_000, 0.8, "asked")
    grouped = handoff_savings.auto_handoff_decisions()
    assert [entry["decision"] for entry in grouped["s1"]] == ["held", "asked"]


def test_a_session_with_two_markers_is_counted_once(tmp_path: Path) -> None:
    old = claude_session(tmp_path / "old.jsonl", "old", [("2026-10-01T11:00:00Z", 400_000)])
    claude_session(tmp_path / "new.jsonl", "new", [("2026-10-01T12:00:00Z", 50_000), ("2026-10-01T12:05:00Z", 60_000)])
    first = marker(old, "old", "2026-10-01T11:01:00Z")
    corrected = {**marker(old, "old", "2026-10-01T11:01:05Z"), "handoff_file": "/work/project/.reference/handoffs/fixed.md"}
    rows = project_savings([first, corrected], [old, tmp_path / "new.jsonl"])
    assert len(rows) == 1 and rows[0]["handoff_file"].endswith("fixed.md")
