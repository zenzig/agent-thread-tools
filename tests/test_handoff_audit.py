from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_thread_tools import handoff_audit, jev


def write(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    return path


def user(text: str, ts: str, **fields) -> dict:
    return {"type": "user", "sessionId": "s1", "cwd": "/work", "timestamp": ts, "message": {"role": "user", "content": text}, **fields}


def assistant(text: str, ts: str) -> dict:
    return {"type": "assistant", "sessionId": "s1", "timestamp": ts, "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def test_items_stop_where_the_handoff_began(tmp_path: Path) -> None:
    session = write(
        tmp_path / "s1.jsonl",
        [
            user("Use Postgres, not SQLite.", "2026-10-01T10:00:00Z"),
            assistant("Switched to Postgres.", "2026-10-01T10:01:00Z"),
            user("Stop hook feedback:\nagent-thread-tools auto-handoff: ...", "2026-10-01T10:02:00Z", isMeta=True),
            assistant("Handoff saved.", "2026-10-01T10:03:00Z"),
        ],
    )
    items = handoff_audit.session_items(session)
    assert [(item["role"], item["text"]) for item in items] == [
        ("user", "Use Postgres, not SQLite."),
        ("assistant", "Switched to Postgres."),
    ]


def test_audit_lists_needed_items_the_handoff_lacks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = write(
        tmp_path / "s1.jsonl",
        [user("Use Postgres, not SQLite.", "2026-10-01T10:00:00Z"), user("thanks", "2026-10-01T10:05:00Z")],
    )
    handoff = tmp_path / "handoff.md"
    handoff.write_text("# Handoff\nNext: add the login page.\n", encoding="utf-8")

    def decide_many(requests, **_):
        out = []
        for state, _questions in requests:
            important = "Postgres" in state["item"]
            out.append({"answers": {"needed": {"noul": 0.9 if important else 0.1}, "reflected": {"noul": 0.05}}, "usage": {"cost": 0.0001}})
        return out

    monkeypatch.setattr(jev, "decide_many", decide_many)
    report = handoff_audit.audit(session, handoff)
    assert report["items_checked"] == 2
    assert [item["text"] for item in report["possibly_missing"]] == ["Use Postgres, not SQLite."]
    assert "Possibly missing (1)" in handoff_audit.format_audit(report)


def test_codex_items_come_from_message_events(tmp_path: Path) -> None:
    session = write(
        tmp_path / "rollout.jsonl",
        [
            {"type": "session_meta", "timestamp": "2026-10-01T10:00:00Z", "payload": {"id": "c1", "cwd": "/work"}},
            {"type": "event_msg", "timestamp": "2026-10-01T10:01:00Z", "payload": {"type": "user_message", "message": "Keep the API stable."}},
            {"type": "event_msg", "timestamp": "2026-10-01T10:02:00Z", "payload": {"type": "agent_message", "message": "Understood."}},
        ],
    )
    assert [item["text"] for item in handoff_audit.session_items(session)] == ["Keep the API stable.", "Understood."]


def message(role: str, text: str) -> dict:
    return {
        "type": "response_item",
        "timestamp": "2026-10-01T10:01:00Z",
        "payload": {"type": "message", "role": role, "content": [{"type": "input_text", "text": text}]},
    }


def test_codex_items_come_from_response_messages_in_newer_rollouts(tmp_path: Path) -> None:
    session = write(
        tmp_path / "rollout.jsonl",
        [
            {"type": "session_meta", "timestamp": "2026-10-01T10:00:00Z", "payload": {"id": "c1", "cwd": "/work"}},
            message("developer", "You are Codex."),
            message("user", "# AGENTS.md instructions for /work"),
            message("user", "<environment_context>cwd</environment_context>"),
            message("user", "Keep the API stable."),
            {"type": "event_msg", "timestamp": "2026-10-01T10:01:00Z", "payload": {"type": "user_message", "message": "Keep the API stable."}},
            message("assistant", "Understood."),
            message("user", "Use the installed `codex-thread-handoff` skill to create a handoff."),
            message("assistant", "Writing the handoff."),
        ],
    )
    assert [item["text"] for item in handoff_audit.session_items(session)] == ["Keep the API stable.", "Understood."]


def test_jev_key_comes_from_the_key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_THREAD_JEV", raising=False)
    key_file = tmp_path / "key"
    key_file.write_text("sk-or-test\n", encoding="utf-8")
    key_file.chmod(0o600)
    monkeypatch.setenv("AGENT_THREAD_JEV_KEY_FILE", str(key_file))
    assert jev.api_key() == "sk-or-test" and jev.available()
    monkeypatch.setenv("AGENT_THREAD_JEV", "off")
    assert not jev.available()


PREVIOUS = """# Old Handoff - 2026-10-04

## Resume Context
Branch at abc123; plan sections awaiting Rich's yes.

## Goal / Next Action
Wait for Rich's device checks (list below).
1. Volume keys change the spoken reply's loudness (X4).
2. Self-test 39/39.

## Current State
Done: X4 shipped.
Current: shipped; device-unverified: X4.

## Decisions
- Use the voice-call stream for speech.

## Open Questions / Risks
- X4 barge-in unverified on device;
  Bluetooth follows the headset's call level.
"""


def test_open_items_are_read_from_the_previous_handoff() -> None:
    items = handoff_audit.open_items(PREVIOUS)
    assert "1. Volume keys change the spoken reply's loudness (X4)." in items
    assert "- X4 barge-in unverified on device; Bluetooth follows the headset's call level." in items
    assert any("Current: shipped; device-unverified: X4." in item for item in items)
    assert not any("voice-call stream" in item for item in items)  # a settled decision
    assert not any("abc123" in item for item in items)  # resume context is state, not open work


def test_the_previous_handoff_is_found_through_claude_local_md(tmp_path: Path) -> None:
    handoffs = tmp_path / ".reference" / "handoffs"
    handoffs.mkdir(parents=True)
    old, new = handoffs / "old.md", handoffs / "new.md"
    old.write_text(PREVIOUS, encoding="utf-8")
    new.write_text("# New\n", encoding="utf-8")
    (tmp_path / "CLAUDE.local.md").write_text("Latest handoff: @.reference/handoffs/old.md\n", encoding="utf-8")
    assert handoff_audit.previous_handoff(new) == old.resolve()
    # Once CLAUDE.local.md points at the new handoff, there is no previous one to check.
    (tmp_path / "CLAUDE.local.md").write_text("Latest handoff: @.reference/handoffs/new.md\n", encoding="utf-8")
    assert handoff_audit.previous_handoff(new) is None


def test_audit_lists_open_items_the_new_handoff_drops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = write(tmp_path / "s.jsonl", [user("Ship it.", "2026-10-05T10:00:00Z")])
    previous = tmp_path / "old.md"
    previous.write_text(PREVIOUS, encoding="utf-8")
    handoff = tmp_path / "new.md"
    handoff.write_text("# New\nX4 device check still owed.\n", encoding="utf-8")

    def decide_many(requests, **_):
        answers = []
        for state, questions in requests:
            reflected = 0.9 if "X4" in state["item"] else 0.1
            result = {"reflected": {"noul": reflected}}
            if "needed" in questions:
                result["needed"] = {"noul": 0.1}
            answers.append({"answers": result})
        return answers

    monkeypatch.setattr(jev, "decide_many", decide_many)
    report = handoff_audit.audit(session, handoff, previous)
    dropped = [item["text"] for item in report["not_carried_forward"]]
    assert "2. Self-test 39/39." in dropped
    assert not any("X4" in text for text in dropped)
    text = handoff_audit.format_audit(report)
    assert "Not carried forward from the previous handoff (old.md)" in text and "- 2. Self-test 39/39." in text
    assert handoff_audit.audit(session, handoff, False)["previous_items_checked"] == 0


def test_jev_retries_a_rate_limited_request(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import urllib.error

    calls = []

    def urlopen(request, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))
        return io.BytesIO(b'{"answers": {}}')

    monkeypatch.setattr(jev.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(jev.time, "sleep", lambda seconds: None)
    assert jev.decide({"x": 1}, {}, key="sk-or-test") == {"answers": {}}
    assert len(calls) == 3
